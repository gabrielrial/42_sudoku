"""Login attempts are rate-limited per IP: 5 per minute (DECISIONS.md D5).

Each test client builds a fresh app, and the limiter lives on the app, so
tests do not share buckets. Tests that move time replace the app's limiter
with one on a fake clock.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.api.routers import users as users_router
from app.config import get_settings
from app.database.models.refresh_tokens import RefreshToken
from app.database.models.users import User
from app.services.rate_limit import RateLimiter
from tests.api.helpers import PASSWORD, login, set_cookies

pytestmark = pytest.mark.db

LIMIT = get_settings().login_attempts_per_minute


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _fake_clock(client: TestClient) -> FakeClock:
    """Give the client's app a fresh login limiter that runs on a fake clock."""
    clock = FakeClock()
    app = client.app
    assert isinstance(app, FastAPI)
    app.state.login_limiter = RateLimiter(capacity=LIMIT, refill_per_second=LIMIT / 60, clock=clock)
    return clock


def _use_up_attempts(client: TestClient) -> None:
    for _ in range(LIMIT):
        assert login(client, "ana", "not-the-password").status_code == 401


def _assert_too_many(response: Response) -> None:
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "too_many_requests"
    assert set_cookies(response) == {}


# --- the limit ---------------------------------------------------------------


def test_the_limit_is_five_per_minute() -> None:
    # D5's figure; the setting exists so it can change without code.
    assert LIMIT == 5


def test_attempts_past_the_limit_are_429(db_client: TestClient, ana: User) -> None:
    _use_up_attempts(db_client)

    _assert_too_many(login(db_client, "ana", "not-the-password"))


def test_even_the_right_password_waits(db: Session, db_client: TestClient, ana: User) -> None:
    _use_up_attempts(db_client)

    _assert_too_many(login(db_client, "ana", PASSWORD))
    assert db.query(RefreshToken).count() == 0


def test_successful_logins_count_too(db_client: TestClient, ana: User) -> None:
    # The limit is on attempts, not on failures.
    for _ in range(LIMIT):
        assert login(db_client, "ana", PASSWORD).status_code == 200

    _assert_too_many(login(db_client, "ana", PASSWORD))


def test_a_limited_attempt_never_reaches_the_password_check(
    db_client: TestClient, ana: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_up_attempts(db_client)
    calls: list[str] = []

    def spy(password: str, password_hash: str) -> bool:
        calls.append(password)
        return False

    monkeypatch.setattr(users_router, "verify_password", spy)

    _assert_too_many(login(db_client, "ana", PASSWORD))
    assert calls == []


# --- refill ------------------------------------------------------------------


def test_one_attempt_comes_back_after_twelve_seconds(db_client: TestClient, ana: User) -> None:
    clock = _fake_clock(db_client)
    _use_up_attempts(db_client)

    clock.advance(60 / LIMIT)

    assert login(db_client, "ana", PASSWORD).status_code == 200
    _assert_too_many(login(db_client, "ana", PASSWORD))


# --- Retry-After -------------------------------------------------------------
# API.md: "Exceeding one gives 429 with Retry-After" -- whole seconds until the
# next attempt would be allowed.


def test_the_429_says_how_long_to_wait(db_client: TestClient, ana: User) -> None:
    _fake_clock(db_client)
    _use_up_attempts(db_client)

    response = login(db_client, "ana", PASSWORD)

    _assert_too_many(response)
    assert response.headers["retry-after"] == "12"


def test_retry_after_counts_down_and_rounds_up(db_client: TestClient, ana: User) -> None:
    clock = _fake_clock(db_client)
    _use_up_attempts(db_client)

    clock.advance(11.5)  # half a second to go
    response = login(db_client, "ana", PASSWORD)

    _assert_too_many(response)
    assert response.headers["retry-after"] == "1"  # never "0": that would invite another 429


# --- scope -------------------------------------------------------------------


def test_other_endpoints_are_not_limited(db_client: TestClient, ana: User) -> None:
    _use_up_attempts(db_client)

    response = db_client.post("/api/users/signup", json={"username": "bob", "password": PASSWORD})

    assert response.status_code == 201


def test_requests_refused_by_the_origin_check_cost_nothing(
    db_client: TestClient, ana: User
) -> None:
    # The origin check runs first: a hostile page cannot burn a user's attempts.
    for _ in range(LIMIT * 2):
        response = db_client.post(
            "/api/users/login",
            data={"username": "ana", "password": PASSWORD},
            headers={"Origin": "https://evil.example"},
        )
        assert response.status_code == 403

    assert login(db_client, "ana", PASSWORD).status_code == 200
