"""``GET /api/auth/login`` is rate-limited per IP, 5 per minute (D5).

Over the limit it does not answer ``429``: the browser arrives by navigation,
so it is sent back to the front end with ``?login_error=too_many_requests``,
like a failed callback (D23). The ``Retry-After`` arithmetic of the other
limits is tested with the game endpoints.

Each test client builds a fresh app, and the limiter lives on the app, so
tests do not share buckets. Tests that move time replace the app's limiter
with one on a fake clock.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_provider
from app.config import get_settings
from app.database.models.oauth_states import OAuthState
from app.services.identity_provider import FakeIdentityProvider
from app.services.rate_limit import RateLimiter
from tests.api.helpers import set_cookies

pytestmark = pytest.mark.db

LIMIT = get_settings().login_attempts_per_minute
LOGIN = "/api/auth/login"
REFUSED = f"{get_settings().frontend_origin}/?login_error=too_many_requests"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def client(db_client: TestClient) -> TestClient:
    """``db_client`` with the fake identity provider, whatever the settings say."""
    app = db_client.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_provider] = FakeIdentityProvider
    return db_client


def _fake_clock(client: TestClient) -> FakeClock:
    """Give the client's app a fresh login limiter that runs on a fake clock."""
    clock = FakeClock()
    app = client.app
    assert isinstance(app, FastAPI)
    app.state.login_limiter = RateLimiter(capacity=LIMIT, refill_per_second=LIMIT / 60, clock=clock)
    return clock


def _attempt(client: TestClient) -> Response:
    return client.get(LOGIN, follow_redirects=False)


def _use_up_attempts(client: TestClient) -> None:
    for _ in range(LIMIT):
        response = _attempt(client)
        assert response.status_code == 302
        assert response.headers["location"] != REFUSED


def _assert_refused(response: Response) -> None:
    assert response.status_code == 302
    assert response.headers["location"] == REFUSED
    assert set_cookies(response) == {}  # no state cookie: nothing was started


# --- the limit ---------------------------------------------------------------


def test_the_limit_is_five_per_minute() -> None:
    # D5's figure; the setting exists so it can change without code.
    assert LIMIT == 5


def test_attempts_past_the_limit_go_back_to_the_front_end(client: TestClient) -> None:
    # Every attempt counts, not only failed ones: here all of them succeed.
    _use_up_attempts(client)

    _assert_refused(_attempt(client))


def test_a_refused_attempt_does_no_work(client: TestClient, db: Session) -> None:
    _use_up_attempts(client)
    states_before = db.scalar(select(func.count()).select_from(OAuthState))

    _assert_refused(_attempt(client))

    assert db.scalar(select(func.count()).select_from(OAuthState)) == states_before


# --- refill ------------------------------------------------------------------


def test_one_attempt_comes_back_after_twelve_seconds(client: TestClient) -> None:
    clock = _fake_clock(client)
    _use_up_attempts(client)

    clock.advance(60 / LIMIT)

    assert _attempt(client).headers["location"] != REFUSED
    _assert_refused(_attempt(client))


# --- scope -------------------------------------------------------------------


def test_other_endpoints_are_not_limited(client: TestClient) -> None:
    # The limit belongs to /login, not to the whole app.
    _use_up_attempts(client)

    assert client.get("/api/health").status_code == 200
