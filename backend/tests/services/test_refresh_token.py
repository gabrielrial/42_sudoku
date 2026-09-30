"""Refresh tokens: issuing and rotating (``app/services/refresh_token.py``).

Every test runs against PostgreSQL through the ``db`` fixture, inside a
transaction that is rolled back afterwards.
"""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.models.refresh_tokens import RefreshToken
from app.database.models.users import User
from app.services.refresh_token import issue_refresh_token, rotate_refresh_token

pytestmark = pytest.mark.db


# --- helpers -----------------------------------------------------------------


def _sha256(raw: str) -> str:
    # Computed here on purpose, not imported: the test pins the storage format.
    return hashlib.sha256(raw.encode()).hexdigest()


def _row(db: Session, raw: str) -> RefreshToken | None:
    """The stored row for a token, looked up the way the server does: by hash."""
    return db.query(RefreshToken).filter(RefreshToken.token_hash == _sha256(raw)).one_or_none()


def _login(db: Session, user: User) -> str:
    """What the login endpoint will do: issue a token, then commit it."""
    raw = issue_refresh_token(db, user.id)
    db.commit()
    return raw


def _assert_rejected(db: Session, raw: str) -> None:
    with pytest.raises(HTTPException) as exc:
        rotate_refresh_token(db, raw)
    assert exc.value.status_code == 401


@pytest.fixture
def user(db: Session) -> User:
    user = User(username="ana", password_hash="not-a-real-hash")
    db.add(user)
    db.commit()
    return user


# --- issue -------------------------------------------------------------------


def test_issue_stores_the_hash_not_the_token(db: Session, user: User) -> None:
    raw = _login(db, user)

    row = _row(db, raw)
    assert row is not None
    assert row.user_id == user.id
    assert row.used_at is None
    assert db.query(RefreshToken).filter(RefreshToken.token_hash == raw).count() == 0


def test_issue_sets_the_expiry_from_settings(db: Session, user: User) -> None:
    before = datetime.now(UTC)
    raw = _login(db, user)

    row = _row(db, raw)
    assert row is not None
    expected = before + timedelta(days=get_settings().refresh_token_days)
    assert expected <= row.expires_at <= expected + timedelta(minutes=1)


def test_each_login_starts_a_new_family(db: Session, user: User) -> None:
    laptop = _row(db, _login(db, user))
    phone = _row(db, _login(db, user))

    assert laptop is not None and phone is not None
    assert laptop.family_id != phone.family_id


def test_issue_with_a_family_keeps_it(db: Session, user: User) -> None:
    family = uuid.uuid4()
    raw = issue_refresh_token(db, user.id, family)
    db.commit()

    row = _row(db, raw)
    assert row is not None
    assert row.family_id == family


# --- rotate: the normal path ---------------------------------------------------


def test_rotate_returns_the_user_and_a_new_token(db: Session, user: User) -> None:
    old = _login(db, user)

    user_id, new = rotate_refresh_token(db, old)

    assert user_id == user.id
    assert new != old


def test_rotate_seals_the_old_token_and_keeps_the_family(db: Session, user: User) -> None:
    old = _login(db, user)

    _, new = rotate_refresh_token(db, old)

    old_row, new_row = _row(db, old), _row(db, new)
    assert old_row is not None and new_row is not None
    assert old_row.used_at is not None
    assert new_row.used_at is None
    assert new_row.family_id == old_row.family_id


def test_the_new_token_can_be_rotated_again(db: Session, user: User) -> None:
    first = _login(db, user)

    _, second = rotate_refresh_token(db, first)
    _, third = rotate_refresh_token(db, second)

    assert third not in {first, second}


# --- rotate: rejections --------------------------------------------------------


def test_unknown_token_is_rejected(db: Session) -> None:
    _assert_rejected(db, "not-a-token-we-issued")


def test_expired_token_is_rejected(db: Session, user: User) -> None:
    raw = _login(db, user)
    row = _row(db, raw)
    assert row is not None
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    _assert_rejected(db, raw)


# --- rotate: reuse means theft -------------------------------------------------


def test_reusing_a_rotated_token_revokes_the_whole_family(db: Session, user: User) -> None:
    old = _login(db, user)
    _, new = rotate_refresh_token(db, old)

    _assert_rejected(db, old)  # someone presents the sealed token again

    assert _row(db, old) is None
    assert _row(db, new) is None  # the token handed out in the rotation is gone too
    _assert_rejected(db, new)


def test_revoking_one_family_leaves_other_devices_alone(db: Session, user: User) -> None:
    laptop = _login(db, user)
    phone = _login(db, user)
    rotate_refresh_token(db, laptop)

    _assert_rejected(db, laptop)  # theft detected on the laptop

    user_id, _ = rotate_refresh_token(db, phone)  # the phone still works
    assert user_id == user.id
