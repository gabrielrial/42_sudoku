from datetime import UTC, datetime, timedelta

import jwt
from fastapi import status
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.models.users import User
from app.errors import APIError

ALGORITHM = "HS256"

settings = get_settings()


def not_authenticated() -> APIError:
    return APIError("not_authenticated", "Authentication required.", status.HTTP_401_UNAUTHORIZED)


def user_from_access_token(db: Session, token: str) -> User:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "iat", "exp"]},
        )
        user_id = int(payload["sub"])
    except (InvalidTokenError, ValueError):
        raise not_authenticated() from None

    user = db.get(User, user_id)
    if user is None:
        raise not_authenticated()
    return user


def create_access_token(user: User) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
