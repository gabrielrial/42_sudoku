"""The 42 sign-in flow: ``GET /api/auth/login`` followed by ``GET /api/auth/callback``.

These tests swap in the fake identity provider (A3), so they never call 42.
In CI ``AUTH_FAKE_PROVIDER_ENABLED`` is off: without the swap, the real
provider would be used. The PKCE tests swap in the real provider instead, with
42 played by ``FakeFortyTwo`` (no network), to see what would reach 42.
"""

import logging
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.cookies import ACCESS_COOKIE, OAUTH_STATE_COOKIE, REFRESH_COOKIE
from app.api.dependencies import get_provider
from app.config import get_settings
from app.database.models.oauth_states import OAuthState
from app.database.models.users import User
from app.services.identity_provider import FakeIdentityProvider, RealIdentityProvider
from app.services.oauth_pkce import code_challenge
from tests.api.helpers import set_cookies
from tests.services.test_identity_provider import ME, FakeFortyTwo

pytestmark = pytest.mark.db

LOGIN = "/api/auth/login"
CALLBACK = "/api/auth/callback"


@pytest.fixture
def oauth_client(db_client: TestClient) -> TestClient:
    """``db_client`` with the fake identity provider, whatever the settings say."""
    app = db_client.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_provider] = FakeIdentityProvider
    return db_client


def _state_from(location: str) -> str:
    """The ``state`` query parameter of the URL /login redirects to."""
    return parse_qs(urlsplit(location).query)["state"][0]


def _saved_state(db: Session, state: str) -> OAuthState | None:
    """The ``oauth_states`` row for ``state``, read from the database (not the session's cache)."""
    return db.scalar(select(OAuthState).where(OAuthState.state == state))


def test_login_saves_the_state_it_sends(oauth_client: TestClient, db: Session) -> None:
    response = oauth_client.get(LOGIN, follow_redirects=False)

    assert response.status_code == 302
    state = _state_from(response.headers["location"])
    # In the app, get_db only closes the session, which throws away anything
    # /login did not commit. rollback() throws away the same thing here.
    db.rollback()
    assert _saved_state(db, state) is not None


def test_login_then_callback_signs_the_user_in(oauth_client: TestClient, db: Session) -> None:
    login = oauth_client.get(LOGIN, follow_redirects=False)
    state = _state_from(login.headers["location"])

    response = oauth_client.get(
        CALLBACK, params={"code": "fake_code", "state": state}, follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["location"] == get_settings().frontend_origin
    cookies = set_cookies(response)
    assert ACCESS_COOKIE in cookies
    assert REFRESH_COOKIE in cookies

    expected = FakeIdentityProvider.IDENTITY
    user = db.scalar(select(User).where(User.intra_id == expected.intra_id))
    assert user is not None
    assert user.login == expected.login
    assert user.campus_name == expected.campus_name
    # A state works once: the callback deletes it.
    assert _saved_state(db, state) is None


# --- PKCE, end to end (D18) -------------------------------------------------------


@pytest.fixture
def fortytwo(db_client: TestClient) -> FakeFortyTwo:
    """42, played without network, behind the real provider of ``db_client``'s app."""
    fake = FakeFortyTwo()
    provider: RealIdentityProvider = fake.provider()
    app = db_client.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_provider] = lambda: provider
    return fake


def test_login_sends_42_the_challenge_of_the_saved_verifier(
    db_client: TestClient, fortytwo: FakeFortyTwo, db: Session
) -> None:
    response = db_client.get(LOGIN, follow_redirects=False)

    query = parse_qs(urlsplit(response.headers["location"]).query)
    row = _saved_state(db, query["state"][0])
    assert row is not None
    assert query["code_challenge"] == [code_challenge(row.code_verifier)]
    assert query["code_challenge_method"] == ["S256"]
    assert row.code_verifier not in response.headers["location"]


def test_callback_sends_42_the_verifier_saved_at_login(
    db_client: TestClient, fortytwo: FakeFortyTwo, db: Session
) -> None:
    login = db_client.get(LOGIN, follow_redirects=False)
    state = _state_from(login.headers["location"])
    saved = _saved_state(db, state)
    assert saved is not None
    verifier = saved.code_verifier

    response = db_client.get(
        CALLBACK, params={"code": "code-from-42", "state": state}, follow_redirects=False
    )

    assert response.status_code == 302
    exchange = parse_qs(fortytwo.requests[0].content.decode())
    assert exchange["code_verifier"] == [verifier]
    assert exchange["code"] == ["code-from-42"]


# --- the state cookie: the login belongs to the browser that started it ---------


def _login(client: TestClient) -> str:
    """Start a login in ``client``; return its state. The cookie lands in its jar."""
    return _state_from(client.get(LOGIN, follow_redirects=False).headers["location"])


def _callback(client: TestClient, state: str | None, **params: str) -> Response:
    """The callback as 42 calls it: with a code, unless ``params`` say otherwise."""
    query = {"code": "code-from-42", **params}
    if state is not None:
        query["state"] = state
    return client.get(CALLBACK, params=query, follow_redirects=False)


def _assert_login_error(response: Response, code: str) -> None:
    """A failed sign-in: back to the front end with the code, signed in to nothing."""
    assert response.status_code == 302
    assert response.headers["location"] == f"{get_settings().frontend_origin}/?login_error={code}"
    cookies = set_cookies(response)
    assert ACCESS_COOKIE not in cookies
    assert REFRESH_COOKIE not in cookies
    assert cookies[OAUTH_STATE_COOKIE]["max-age"] == "0"  # the attempt is over either way


def _assert_refused(response: Response) -> None:
    _assert_login_error(response, "invalid_state")


def _user_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User)) or 0


def test_login_puts_the_state_in_a_cookie_only_the_callback_receives(
    db_client: TestClient, fortytwo: FakeFortyTwo
) -> None:
    response = db_client.get(LOGIN, follow_redirects=False)

    cookie = set_cookies(response)[OAUTH_STATE_COOKIE]
    assert cookie["value"] == _state_from(response.headers["location"])
    assert cookie["path"] == "/api/auth/callback"
    assert cookie["max-age"] == "600"  # the state's own ten minutes
    assert "httponly" in cookie
    assert cookie["samesite"] == "lax"


def test_a_successful_callback_clears_the_state_cookie(
    db_client: TestClient, fortytwo: FakeFortyTwo
) -> None:
    response = _callback(db_client, _login(db_client))

    assert response.status_code == 302
    cookie = set_cookies(response)[OAUTH_STATE_COOKIE]
    assert cookie["max-age"] == "0"
    assert cookie["path"] == "/api/auth/callback"


def test_a_callback_without_the_state_cookie_is_refused(
    db_client: TestClient, fortytwo: FakeFortyTwo
) -> None:
    state = _login(db_client)
    db_client.cookies.clear()

    _assert_refused(_callback(db_client, state))
    assert fortytwo.requests == []  # refused before 42 is ever asked


def test_an_attackers_state_does_not_sign_the_victim_in(
    db_client: TestClient, fortytwo: FakeFortyTwo
) -> None:
    # Login CSRF (LESSONS.md E): the attacker starts a login and sends the
    # victim the callback link with the attacker's own, perfectly valid, state.
    attackers_state = _login(db_client)
    db_client.cookies.clear()
    _login(db_client)  # the victim's browser holds a state of its own

    _assert_refused(_callback(db_client, attackers_state))
    assert fortytwo.requests == []


def test_a_state_that_is_not_ascii_is_refused_not_an_error(
    db_client: TestClient, fortytwo: FakeFortyTwo
) -> None:
    _login(db_client)

    _assert_refused(_callback(db_client, "état"))


def test_a_state_is_spent_even_when_42_fails(
    db: Session, db_client: TestClient, fortytwo: FakeFortyTwo
) -> None:
    fortytwo.token = lambda _: httpx.Response(503)
    state = _login(db_client)
    _assert_login_error(_callback(db_client, state), "provider_error")
    # In the app, get_db closes the session and drops whatever was not
    # committed. rollback() drops the same thing here.
    db.rollback()

    db_client.cookies.set(OAUTH_STATE_COOKIE, state)  # a replay brings the cookie back too
    _assert_refused(_callback(db_client, state))
    assert len(fortytwo.requests) == 1  # 42 was asked once, never again


# --- every other way a sign-in can fail: back to the front end with a code -------


def test_a_callback_without_a_state_is_refused(
    db_client: TestClient, fortytwo: FakeFortyTwo
) -> None:
    _login(db_client)

    _assert_refused(_callback(db_client, None))
    assert fortytwo.requests == []


def test_a_denied_consent_says_so(db_client: TestClient, fortytwo: FakeFortyTwo) -> None:
    # The user pressed "cancel" at 42: it comes back with error, not code.
    state = _login(db_client)

    response = db_client.get(
        CALLBACK, params={"error": "access_denied", "state": state}, follow_redirects=False
    )

    _assert_login_error(response, "access_denied")
    assert fortytwo.requests == []


def test_a_denied_consent_spends_the_state(db_client: TestClient, fortytwo: FakeFortyTwo) -> None:
    state = _login(db_client)
    _callback(db_client, state, error="access_denied")

    db_client.cookies.set(OAUTH_STATE_COOKIE, state)
    _assert_refused(_callback(db_client, state))


def test_any_other_error_from_42_is_a_provider_error(
    db_client: TestClient, fortytwo: FakeFortyTwo
) -> None:
    state = _login(db_client)

    response = db_client.get(
        CALLBACK, params={"error": "server_error", "state": state}, follow_redirects=False
    )

    _assert_login_error(response, "provider_error")


def test_a_callback_with_neither_code_nor_error_is_a_provider_error(
    db_client: TestClient, fortytwo: FakeFortyTwo
) -> None:
    state = _login(db_client)

    response = db_client.get(CALLBACK, params={"state": state}, follow_redirects=False)

    _assert_login_error(response, "provider_error")
    assert fortytwo.requests == []


def test_a_code_42_refuses_signs_nobody_in(
    db: Session, db_client: TestClient, fortytwo: FakeFortyTwo
) -> None:
    fortytwo.token = lambda _: httpx.Response(400, json={"error": "invalid_grant"})
    users_before = _user_count(db)

    _assert_login_error(_callback(db_client, _login(db_client)), "provider_error")
    assert _user_count(db) == users_before


def test_an_account_without_a_primary_campus_is_turned_away(
    db: Session, db_client: TestClient, fortytwo: FakeFortyTwo
) -> None:
    me = dict(ME, campus_users=[{"campus_id": 21, "is_primary": False}])
    fortytwo.me = lambda _: httpx.Response(200, json=me)
    users_before = _user_count(db)

    _assert_login_error(_callback(db_client, _login(db_client)), "no_primary_campus")
    assert _user_count(db) == users_before


def test_a_failure_is_logged_without_anything_secret(
    db_client: TestClient, fortytwo: FakeFortyTwo, caplog: pytest.LogCaptureFixture
) -> None:
    fortytwo.token = lambda _: httpx.Response(503)
    state = _login(db_client)

    with caplog.at_level(logging.WARNING, logger="app.api.routers.auth"):
        _callback(db_client, state)

    assert "provider_error" in caplog.text
    for secret in (state, "code-from-42", "client-secret-456"):
        assert secret not in caplog.text


def test_an_error_from_the_url_cannot_forge_log_lines(
    db_client: TestClient, fortytwo: FakeFortyTwo, caplog: pytest.LogCaptureFixture
) -> None:
    state = _login(db_client)

    with caplog.at_level(logging.WARNING, logger="app.api.routers.auth"):
        _callback(db_client, state, error="x\nCRITICAL everything is on fire")

    assert len(caplog.records) == 1
    assert "\n" not in caplog.records[0].getMessage()
