import math

from fastapi import Request, status

from app.errors import APIError
from app.services.rate_limit import RateLimiter


def limit_login_attempts(request: Request) -> None:
    """Per-IP limit on login attempts; 429 once the bucket is empty."""
    limiter: RateLimiter = request.app.state.login_limiter
    ip = request.client.host if request.client else "unknown"
    enforce(limiter, ip, "Too many login attempts. Try again later.")


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
