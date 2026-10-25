import math

from fastapi import Request, status

from app.errors import APIError
from app.services.rate_limit import RateLimiter


def take_login_attempt(request: Request) -> bool:
    """One login attempt from the caller's IP (D5); ``False`` once its bucket is
    empty. The caller answers the refusal: ``/login`` is reached by navigation,
    so it redirects rather than answering ``429`` (D23)."""
    limiter: RateLimiter = request.app.state.login_limiter
    ip = request.client.host if request.client else "unknown"
    return limiter.allow(ip)


def enforce(limiter: RateLimiter, key: str, message: str) -> None:
    """Take one token from ``key``'s bucket, or answer 429 with ``Retry-After``
    in whole seconds, rounded up (D17)."""
    if not limiter.allow(key):
        wait = limiter.seconds_until_allowed(key)
        raise APIError(
            "too_many_requests",
            message,
            status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(math.ceil(wait))},
        )
