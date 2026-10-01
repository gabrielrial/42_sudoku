from fastapi import Request, status

from app.config import get_settings
from app.errors import APIError

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def require_frontend_origin(request: Request) -> None:
    """Second CSRF layer after SameSite=Lax: state changes only from the front end."""
    if request.method in SAFE_METHODS:
        return
    if request.headers.get("origin") != get_settings().frontend_origin:
        raise APIError("forbidden_origin", "Request origin not allowed.", status.HTTP_403_FORBIDDEN)
