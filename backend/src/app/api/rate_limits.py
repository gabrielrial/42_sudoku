from fastapi import Request, status

from app.errors import APIError
from app.services.rate_limit import RateLimiter


def limit_login_attempts(request: Request) -> None:
    """Per-IP limit on login attempts; 429 once the bucket is empty."""
    limiter: RateLimiter = request.app.state.login_limiter
    ip = request.client.host if request.client else "unknown"
    if not limiter.allow(ip):
        raise APIError(
            "too_many_requests",
            "Too many login attempts. Try again later.",
            status.HTTP_429_TOO_MANY_REQUESTS,
        )
