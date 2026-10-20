import logging
import secrets
from typing import Annotated
from urllib.parse import urlencode

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
from app.services.identity_provider import (
    IdentityProvider,
    IdentityProviderError,
    NoPrimaryCampus,
)
from app.services.oauth_pkce import InvalidOAuthState, finish_login, start_login
from app.services.refresh_token import (
    issue_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])

logger = logging.getLogger(__name__)


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
    db: Annotated[Session, Depends(get_db)],
    provider: ProviderDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    state_cookie: Annotated[str | None, Cookie(alias=OAUTH_STATE_COOKIE)] = None,
) -> RedirectResponse:
    """Where 42 sends the browser back. Every outcome is a redirect to the front
    end: its home page when signed in, ``?login_error=<code>`` otherwise
    (``API.md``). Nothing about a failure beyond that code leaves the server."""
    try:
        access_token, refresh_token = _sign_in(
            db, provider, code=code, state=state, error=error, state_cookie=state_cookie
        )
    except _LoginFailed as failed:
        logger.warning("42 sign-in failed (%s): %s", failed.code, failed)
        redirect = _to_front_end(login_error=failed.code)
    else:
        redirect = _to_front_end()
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


# --- the callback's work ----------------------------------------------------------

# The codes the front end can receive in ``?login_error=`` (API.md).
INVALID_STATE = "invalid_state"
ACCESS_DENIED = "access_denied"
PROVIDER_ERROR = "provider_error"
NO_PRIMARY_CAMPUS = "no_primary_campus"


class _LoginFailed(Exception):
    """A sign-in that ends in ``?login_error=code``. The message is for the log."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code


def _sign_in(
    db: Session,
    provider: IdentityProvider,
    *,
    code: str | None,
    state: str | None,
    error: str | None,
    state_cookie: str | None,
) -> tuple[str, str]:
    """Everything the callback checks, in order. Returns the access and refresh
    tokens of the user who signed in; raises ``_LoginFailed``."""
    # The state must be the one this browser was given at /login, not merely
    # one the server issued: otherwise an attacker's own valid state, in a link
    # sent to a victim, signs the victim in to the attacker's account.
    if state is None or state_cookie is None or not _same(state_cookie, state):
        raise _LoginFailed(INVALID_STATE, "state missing, or not the one this browser was given")
    try:
        code_verifier = finish_login(db, state)
    except InvalidOAuthState:
        raise _LoginFailed(INVALID_STATE, "state unknown, already used or expired") from None
    # Spent before 42 is called: if anything below fails, the state stays used.
    db.commit()

    # 42 reports a refusal by redirecting with ``error`` instead of ``code``
    # (RFC 6749, section 4.1.2.1). Anyone can put anything in a URL, so the
    # value is only logged shortened and quoted.
    if error is not None:
        failure = ACCESS_DENIED if error == "access_denied" else PROVIDER_ERROR
        raise _LoginFailed(failure, f"42 redirected with error={error[:64]!r}")
    if code is None:
        raise _LoginFailed(PROVIDER_ERROR, "42 redirected with neither code nor error")

    try:
        identity = provider.identity_from_code(code, code_verifier)
    except NoPrimaryCampus as exc:
        raise _LoginFailed(NO_PRIMARY_CAMPUS, str(exc)) from None
    except IdentityProviderError as exc:
        raise _LoginFailed(PROVIDER_ERROR, str(exc)) from None

    user = db.query(User).filter(User.intra_id == identity.intra_id).first()
    if not user:
        user = User(
            intra_id=identity.intra_id,
            login=identity.login,
            campus_id=identity.campus_id,
            campus_name=identity.campus_name,
        )
        db.add(user)
    db.flush()  # a new user gets its id here, for the refresh token
    refresh_token = issue_refresh_token(db, user.id)
    db.commit()  # the user and their session together, or neither
    return create_access_token(user), refresh_token


def _same(a: str, b: str) -> bool:
    """Constant-time comparison. Bytes, because ``compare_digest`` refuses
    non-ASCII ``str`` and the URL's ``state`` is whatever the caller sent."""
    return secrets.compare_digest(a.encode(), b.encode())


def _to_front_end(**query: str) -> RedirectResponse:
    url = get_settings().frontend_origin
    if query:
        url = f"{url}/?{urlencode(query)}"
    return RedirectResponse(url, status_code=302)
