from datetime import UTC, datetime, timedelta

import jwt
from fastapi import HTTPException
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.user import get_user_by_username

ALGORITHM = "HS256"

credentials_exception = HTTPException(
    status_code=401,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

settings = get_settings()


def _user_from_token(token: str, db: Session):
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])

        username: str | None = payload.get("sub")

        if not username:
            raise credentials_exception

    except InvalidTokenError:
        raise credentials_exception from None

    user = get_user_by_username(db, username)

    if not user:
        raise credentials_exception

    return user


def create_access_token(data: dict):
    payload = data.copy()

    payload["exp"] = datetime.now(UTC) + timedelta(minutes=settings.access_token_minutes)

    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
