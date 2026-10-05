from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.cookies import REFRESH_COOKIE, clear_auth_cookies, set_auth_cookies
from app.database.conf.dependencies import get_db
from app.database.models.users import User
from app.database.schema.user import UserPublic
from app.services.auth import create_access_token, not_authenticated
from app.services.refresh_token import revoke_refresh_token, rotate_refresh_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/refresh", response_model=UserPublic)
def refresh(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> User:
    if not refresh_token:
        raise not_authenticated()

    user_id, new_refresh = rotate_refresh_token(db, refresh_token)

    user = db.get(User, user_id)
    if user is None:
        raise not_authenticated()

    access_token = create_access_token(user)
    set_auth_cookies(response, access_token, new_refresh)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> None:
    clear_auth_cookies(response)
    if refresh_token:
        revoke_refresh_token(db, refresh_token)
