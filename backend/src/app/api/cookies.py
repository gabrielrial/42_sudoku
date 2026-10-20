from fastapi import Response

from app.config import get_settings
from app.services.oauth_pkce import STATE_LIFETIME

settings = get_settings()

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"

ACCESS_PATH = "/"
REFRESH_PATH = "/api/auth"

# Ties a login to the browser that started it (DATA_MODEL.md, oauth_states):
# the callback only accepts a ``state`` this browser was given. Sent to the
# callback and nowhere else.
OAUTH_STATE_COOKIE = "oauth_state"
OAUTH_STATE_PATH = "/api/auth/callback"


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        key=ACCESS_COOKIE,
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        max_age=settings.access_token_minutes * 60,
        path=ACCESS_PATH,
    )
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        max_age=settings.refresh_token_days * 24 * 3600,
        path=REFRESH_PATH,
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(
        key=ACCESS_COOKIE,
        path=ACCESS_PATH,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
    )
    response.delete_cookie(
        key=REFRESH_COOKIE,
        path=REFRESH_PATH,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
    )


def set_oauth_state_cookie(response: Response, state: str) -> None:
    response.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=state,
        httponly=True,
        samesite="lax",  # 42 sends the browser back by a top-level GET, which Lax allows
        secure=settings.is_production,
        max_age=int(STATE_LIFETIME.total_seconds()),
        path=OAUTH_STATE_PATH,
    )


def clear_oauth_state_cookie(response: Response) -> None:
    response.delete_cookie(
        key=OAUTH_STATE_COOKIE,
        path=OAUTH_STATE_PATH,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
    )
