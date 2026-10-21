"""``upsert_user``: the ``users`` row follows 42 at every sign-in (``app/services/users.py``).

The provider is a ``Directory``: it only answers ``current_login``, from a
dict, and records who it was asked about. Every test runs against PostgreSQL
through the ``db`` fixture, so the unique constraint on ``login`` is the real one.
"""

import logging

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.users import User
from app.services.identity_provider import Identity, IdentityProviderError
from app.services.users import placeholder_login, upsert_user

pytestmark = pytest.mark.db

ANA = Identity(intra_id=222, login="ana", campus_id=51, campus_name="Berlin")


class Directory:
    """42's answer to "what is account N called today?"."""

    def __init__(self, logins: dict[int, str] | None = None, down: bool = False) -> None:
        self.logins = logins or {}
        self.down = down
        self.asked: list[int] = []

    def current_login(self, intra_id: int) -> str | None:
        self.asked.append(intra_id)
        if self.down:
            raise IdentityProviderError("42 request failed: ConnectError")
        return self.logins.get(intra_id)


def _save(db: Session, intra_id: int, login: str) -> User:
    user = User(intra_id=intra_id, login=login, campus_id=21, campus_name="Paris")
    db.add(user)
    db.commit()
    return user


def _login_of(db: Session, intra_id: int) -> str | None:
    db.expire_all()  # read the table, not the session's cache
    return db.scalar(select(User.login).where(User.intra_id == intra_id))


def _upsert(db: Session, identity: Identity, directory: Directory) -> User:
    user = upsert_user(db, identity, directory)  # type: ignore[arg-type]
    db.commit()  # the constraint is checked for real
    return user


# --- the ordinary cases --------------------------------------------------------------


def test_a_first_sign_in_creates_the_user(db: Session) -> None:
    user = _upsert(db, ANA, Directory())

    assert (user.intra_id, user.login, user.campus_id, user.campus_name) == (
        222,
        "ana",
        51,
        "Berlin",
    )


def test_a_returning_user_gets_their_new_login_and_campus(db: Session) -> None:
    before = _save(db, 222, "ana-old")

    user = _upsert(db, ANA, Directory())

    assert user.id == before.id  # the same person: matched on intra_id
    assert (user.login, user.campus_id, user.campus_name) == ("ana", 51, "Berlin")


def test_without_a_collision_42_is_not_asked_anything_more(db: Session) -> None:
    directory = Directory()
    _save(db, 333, "bob")

    _upsert(db, ANA, directory)

    assert directory.asked == []


# --- one login, two accounts: 42 decides ------------------------------------------------


def test_a_newcomer_takes_the_login_and_the_old_holder_gets_their_new_one(db: Session) -> None:
    # 111 was "ana", became "ana-m" at 42, and 42 gave "ana" to 222.
    _save(db, 111, "ana")
    directory = Directory({111: "ana-m"})

    _upsert(db, ANA, directory)

    assert _login_of(db, 222) == "ana"
    assert _login_of(db, 111) == "ana-m"
    assert directory.asked == [111]


@pytest.mark.parametrize("returning_user_joined_first", [False, True])
def test_a_returning_user_renamed_into_a_taken_login_also_takes_it(
    db: Session, returning_user_joined_first: bool
) -> None:
    # Who joined first decides which row has the lower id, and so the order in
    # which a single flush would write them. The result must not depend on it.
    if returning_user_joined_first:
        _save(db, 222, "ana-old")
        _save(db, 111, "ana")
    else:
        _save(db, 111, "ana")
        _save(db, 222, "ana-old")

    _upsert(db, ANA, Directory({111: "ana-m"}))

    assert _login_of(db, 222) == "ana"
    assert _login_of(db, 111) == "ana-m"


# --- when 42's answer cannot be used: a placeholder, and the sign-in goes on -----------

UNUSABLE: dict[str, Directory] = {
    "42 does not know the account": Directory({}),
    "42 is down": Directory(down=True),
    "42 says the old holder is still ana": Directory({111: "ana"}),
}


@pytest.mark.parametrize("directory", UNUSABLE.values(), ids=UNUSABLE.keys())
def test_the_old_holder_gets_a_placeholder(db: Session, directory: Directory) -> None:
    _save(db, 111, "ana")

    _upsert(db, ANA, directory)

    assert _login_of(db, 222) == "ana"
    assert _login_of(db, 111) == placeholder_login(111) == "former-111"


def test_a_new_login_taken_here_too_is_not_chased(db: Session) -> None:
    _save(db, 111, "ana")
    _save(db, 333, "ana-m")  # stale as well, but nobody is signing in as 333

    _upsert(db, ANA, Directory({111: "ana-m"}))

    assert _login_of(db, 111) == "former-111"
    assert _login_of(db, 333) == "ana-m"  # untouched


def test_the_old_holder_puts_things_right_at_their_own_next_sign_in(db: Session) -> None:
    _save(db, 111, "ana")
    _upsert(db, ANA, Directory(down=True))
    assert _login_of(db, 111) == "former-111"

    _upsert(db, Identity(111, "ana-m", 21, "Paris"), Directory())

    assert _login_of(db, 111) == "ana-m"


def test_a_takeover_is_logged_by_id(db: Session, caplog: pytest.LogCaptureFixture) -> None:
    _save(db, 111, "ana")

    with caplog.at_level(logging.WARNING, logger="app.services.users"):
        _upsert(db, ANA, Directory({111: "ana-m"}))

    assert "intra_id 222 now holds it" in caplog.text
    assert "intra_id 111 renamed" in caplog.text
