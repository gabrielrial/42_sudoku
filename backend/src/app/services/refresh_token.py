import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.models.refresh_tokens import RefreshToken
from app.services.auth import not_authenticated

settings = get_settings()


def _token_expired(refresh_token: RefreshToken) -> bool:
    return datetime.now(UTC) >= refresh_token.expires_at


def _random_value() -> str:
    return secrets.token_urlsafe(32)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_refresh_token(db: Session, user_id: int, family_id: uuid.UUID | None = None) -> str:
    raw = _random_value()
    family_id = family_id or uuid.uuid4()
    refresh_token = RefreshToken(
        user_id=user_id,
        token_hash=_hash_token(raw),
        family_id=family_id,
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
    )
    db.add(refresh_token)

    return raw


def rotate_refresh_token(db: Session, raw: str) -> tuple[int, str]:
    token = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == _hash_token(raw))
        .with_for_update()
        .first()
    )

    if not token:
        raise not_authenticated()

    if token.used_at is not None:
        db.query(RefreshToken).filter(RefreshToken.family_id == token.family_id).delete()
        db.commit()
        raise not_authenticated()

    if _token_expired(token):
        raise not_authenticated()

    token.used_at = datetime.now(UTC)

    new_raw = issue_refresh_token(db, token.user_id, token.family_id)
    db.commit()

    return token.user_id, new_raw


def revoke_refresh_token(db: Session, raw: str) -> None:
    token = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == _hash_token(raw))
        .with_for_update()
        .first()
    )
    if token:
        db.query(RefreshToken).filter(RefreshToken.family_id == token.family_id).delete()
        db.commit()

    return
