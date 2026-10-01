from fastapi import Response

from app.config import get_settings

settings = get_settings()

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"

ACCESS_PATH = "/"
REFRESH_PATH = "/api/auth"


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
