"""``limit_login_attempts``: login attempts are rate-limited per IP, 5 per minute (D5).

The dependency is tested on a route that exists only in these tests, so they
do not depend on how people sign in (D16: the password login goes away, and
the 42 login will use this same limit). An endpoint that uses the limit only
needs one test of its own saying that it is limited.

Each test client builds a fresh app, and the limiter lives on the app, so
tests do not share buckets. Tests that move time replace the app's limiter
with one on a fake clock. No database: the limited route does nothing.
"""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from httpx import Response

from app.api.rate_limits import limit_login_attempts
from app.config import get_settings
from app.services.rate_limit import RateLimiter
from tests.api.helpers import error_code, set_cookies

LIMIT = get_settings().login_attempts_per_minute

LIMITED = "/api/test-only/limited"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def reached() -> list[str]:
    """One entry per request that got past the limit into the limited route."""
    return []


@pytest.fixture
def limited(client: TestClient, reached: list[str]) -> TestClient:
    """``client``, whose app has a POST route behind ``limit_login_attempts``.

    The route is added to the real app, so the app's global dependencies (the
    origin check) run before the limit, as they do for any real endpoint.
    """

    def endpoint() -> dict[str, str]:
        reached.append("in")
        return {"status": "ok"}

    app = client.app
    assert isinstance(app, FastAPI)
    app.add_api_route(
        LIMITED, endpoint, methods=["POST"], dependencies=[Depends(limit_login_attempts)]
    )
    return client


def _fake_clock(client: TestClient) -> FakeClock:
    """Give the client's app a fresh login limiter that runs on a fake clock."""
    clock = FakeClock()
    app = client.app
    assert isinstance(app, FastAPI)
    app.state.login_limiter = RateLimiter(capacity=LIMIT, refill_per_second=LIMIT / 60, clock=clock)
    return clock


def _attempt(client: TestClient) -> Response:
    return client.post(LIMITED)


def _use_up_attempts(client: TestClient) -> None:
    for _ in range(LIMIT):
        assert _attempt(client).status_code == 200


def _assert_too_many(response: Response) -> None:
    assert response.status_code == 429
    assert error_code(response) == "too_many_requests"
    assert set_cookies(response) == {}


# --- the limit ---------------------------------------------------------------


def test_the_limit_is_five_per_minute() -> None:
    # D5's figure; the setting exists so it can change without code.
    assert LIMIT == 5


def test_attempts_past_the_limit_are_429(limited: TestClient) -> None:
    # Every attempt counts, not only failed ones: here all of them succeed.
    _use_up_attempts(limited)

    _assert_too_many(_attempt(limited))


def test_a_limited_attempt_never_reaches_the_endpoint(
    limited: TestClient, reached: list[str]
) -> None:
    _use_up_attempts(limited)

    _assert_too_many(_attempt(limited))
    assert len(reached) == LIMIT


# --- refill ------------------------------------------------------------------


def test_one_attempt_comes_back_after_twelve_seconds(limited: TestClient) -> None:
    clock = _fake_clock(limited)
    _use_up_attempts(limited)

    clock.advance(60 / LIMIT)

    assert _attempt(limited).status_code == 200
    _assert_too_many(_attempt(limited))


# --- Retry-After -------------------------------------------------------------
# API.md: "Exceeding one gives 429 with Retry-After" -- whole seconds until the
# next attempt would be allowed.


def test_the_429_says_how_long_to_wait(limited: TestClient) -> None:
    _fake_clock(limited)
    _use_up_attempts(limited)

    response = _attempt(limited)

    _assert_too_many(response)
    assert response.headers["retry-after"] == "12"


def test_retry_after_counts_down_and_rounds_up(limited: TestClient) -> None:
    clock = _fake_clock(limited)
    _use_up_attempts(limited)

    clock.advance(11.5)  # half a second to go
    response = _attempt(limited)

    _assert_too_many(response)
    assert response.headers["retry-after"] == "1"  # never "0": that would invite another 429


# --- scope -------------------------------------------------------------------


def test_other_endpoints_are_not_limited(limited: TestClient) -> None:
    # The limit belongs to the routes that declare it, not to the whole app.
    _use_up_attempts(limited)

    assert limited.get("/api/health").status_code == 200


def test_requests_refused_by_the_origin_check_cost_nothing(
    limited: TestClient, reached: list[str]
) -> None:
    # The origin check runs first: a hostile page cannot burn a user's attempts.
    for _ in range(LIMIT * 2):
        response = limited.post(LIMITED, headers={"Origin": "https://evil.example"})
        assert response.status_code == 403

    assert _attempt(limited).status_code == 200
    assert reached == ["in"]
