from typing import Annotated

from fastapi import Cookie, Depends
from sqlalchemy.orm import Session

from app.api.cookies import ACCESS_COOKIE
from app.database.conf.dependencies import get_db
from app.database.models.users import User
from app.services.auth import not_authenticated, user_from_access_token


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
) -> User:
    if not access_token:
        raise not_authenticated()
    return user_from_access_token(db, access_token)
