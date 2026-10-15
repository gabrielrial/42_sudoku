from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.api.cookies import REFRESH_COOKIE, clear_auth_cookies, set_auth_cookies
from app.api.dependencies import ProviderDep
from app.config import Settings
from app.database.conf.dependencies import get_db
from app.database.models.users import User
from app.database.schema.user import UserPublic
from app.services.auth import create_access_token, not_authenticated
from app.services.oauth_pkce import InvalidOAuthState, finish_login, start_login
from app.services.refresh_token import (
    issue_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])

settings = Settings()


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


@router.get("/callback")
def callback(
    code: str,
    state: str,
    db: Annotated[Session, Depends(get_db)],
    provider: ProviderDep,
) -> RedirectResponse:
    try:
        finish_login(db, state)
    except InvalidOAuthState:
        raise not_authenticated() from None

    identity = provider.identity_from_code(code)

    user = db.query(User).filter(User.intra_id == identity.intra_id).first()
    if not user:
        user = User(
            intra_id=identity.intra_id,
            login=identity.login,
            campus_id=identity.campus_id,
            campus_name=identity.campus_name,
        )
        db.add(user)
    db.commit()

    access_token = create_access_token(user)
    refresh_token = issue_refresh_token(db, user.id)
    db.commit()

    redirect = RedirectResponse(url=settings.frontend_origin, status_code=302)

    set_auth_cookies(redirect, access_token, refresh_token)

    return redirect


@router.get("/login")
def login(db: Annotated[Session, Depends(get_db)], provider: ProviderDep) -> RedirectResponse:

    state = start_login(db)
    db.commit()
    url = provider.authorize_url(state[0])

    return RedirectResponse(url, status_code=302)
