"""Access tokens: creating and reading them (``app/services/auth.py``).

Creating a token needs no database. Reading one ends in a database lookup, so
those tests take the ``db`` and ``user`` fixtures.

Every rejected token below is built for a user that *does* exist. That way the
only thing wrong with it is the one thing the test names: if that check were
missing, the lookup would succeed and the test would fail.
"""

import base64
import json
from collections.abc import Callable
from datetime import UTC, datetime

import jwt
import pytest
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.models.users import User
from app.errors import APIError
from app.services.auth import create_access_token, user_from_access_token

settings = get_settings()


# --- helpers -----------------------------------------------------------------

_DROP = object()  # marks a claim to leave out


def _now() -> int:
    return int(datetime.now(UTC).timestamp())


def _claims(user_id: int, **changes: object) -> dict[str, object]:
    """Claims of a valid token for ``user_id``, with ``changes`` applied."""
    now = _now()
    claims: dict[str, object] = {"sub": str(user_id), "iat": now, "exp": now + 900}
    for name, value in changes.items():
        if value is _DROP:
            claims.pop(name)
        else:
            claims[name] = value
    return claims


def _sign(claims: dict[str, object], key: str | None = None, algorithm: str = "HS256") -> str:
    return jwt.encode(claims, key or settings.secret_key, algorithm=algorithm)


def _unsigned(claims: dict[str, object]) -> str:
    """A token that says ``"alg": "none"`` and carries no signature at all."""

    def part(data: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'none', 'typ': 'JWT'})}.{part(claims)}."


# --- create ------------------------------------------------------------------


def test_the_token_names_the_user_by_id() -> None:
    token = create_access_token(User(id=5))

    claims = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    assert claims["sub"] == "5"


def test_the_token_lasts_the_configured_minutes() -> None:
    token = create_access_token(User(id=5))

    claims = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    assert claims["exp"] - claims["iat"] == settings.access_token_minutes * 60


def test_the_token_is_signed_with_hs256() -> None:
    token = create_access_token(User(id=5))

    assert jwt.get_unverified_header(token)["alg"] == "HS256"


# --- read: accepted ----------------------------------------------------------


@pytest.mark.db
def test_a_token_we_created_gives_back_its_user(db: Session, user: User) -> None:
    token = create_access_token(user)

    assert user_from_access_token(db, token).id == user.id


@pytest.mark.db
def test_the_test_helpers_build_a_valid_token(db: Session, user: User) -> None:
    # Control case: the rejections below differ from this token in one thing only.
    assert user_from_access_token(db, _sign(_claims(user.id))).id == user.id


# --- read: rejected ----------------------------------------------------------

REJECTED: dict[str, Callable[[int], str]] = {
    "not a JWT": lambda uid: "not-a-jwt",
    "expired": lambda uid: _sign(_claims(uid, exp=_now() - 1)),
    "signed with another key": lambda uid: _sign(_claims(uid), key="another-key-" + "x" * 32),
    "signed with HS512": lambda uid: _sign(_claims(uid), algorithm="HS512"),
    "unsigned (alg none)": lambda uid: _unsigned(_claims(uid)),
    "without sub": lambda uid: _sign(_claims(uid, sub=_DROP)),
    "without iat": lambda uid: _sign(_claims(uid, iat=_DROP)),
    "without exp": lambda uid: _sign(_claims(uid, exp=_DROP)),
    "sub is not a number": lambda uid: _sign(_claims(uid, sub="abc")),
    "user does not exist": lambda uid: _sign(_claims(uid + 1000)),
}


@pytest.mark.db
@pytest.mark.parametrize("make_token", REJECTED.values(), ids=REJECTED.keys())
def test_bad_tokens_are_rejected(db: Session, user: User, make_token: Callable[[int], str]) -> None:
    with pytest.raises(APIError) as exc:
        user_from_access_token(db, make_token(user.id))
    assert exc.value.http_status == 401
    assert exc.value.code == "not_authenticated"
