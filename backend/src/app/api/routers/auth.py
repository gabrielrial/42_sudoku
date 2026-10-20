import secrets
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.api.cookies import (
    OAUTH_STATE_COOKIE,
    REFRESH_COOKIE,
    clear_auth_cookies,
    clear_oauth_state_cookie,
    set_auth_cookies,
    set_oauth_state_cookie,
)
from app.api.dependencies import ProviderDep
from app.config import get_settings
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
    state_cookie: Annotated[str | None, Cookie(alias=OAUTH_STATE_COOKIE)] = None,
) -> RedirectResponse:
    # The state must be the one this browser was given at /login, not merely
    # one the server issued: otherwise an attacker's own valid state, in a link
    # sent to a victim, signs the victim in to the attacker's account.
    if state_cookie is None or not _same(state_cookie, state):
        raise not_authenticated()

    try:
        code_verifier = finish_login(db, state)
    except InvalidOAuthState:
        raise not_authenticated() from None
    # Spent before 42 is called: if anything below fails, the state stays used.
    db.commit()

    identity = provider.identity_from_code(code, code_verifier)

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

    redirect = RedirectResponse(url=get_settings().frontend_origin, status_code=302)

    set_auth_cookies(redirect, access_token, refresh_token)
    clear_oauth_state_cookie(redirect)

    return redirect


@router.get("/login")
def login(db: Annotated[Session, Depends(get_db)], provider: ProviderDep) -> RedirectResponse:
    state, code_challenge = start_login(db)
    db.commit()
    url = provider.authorize_url(state, code_challenge)

    redirect = RedirectResponse(url, status_code=302)
    set_oauth_state_cookie(redirect, state)
    return redirect


def _same(a: str, b: str) -> bool:
    """Constant-time comparison. Bytes, because ``compare_digest`` refuses
    non-ASCII ``str`` and the URL's ``state`` is whatever the caller sent."""
    return secrets.compare_digest(a.encode(), b.encode())
