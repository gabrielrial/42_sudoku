"""The 42 sign-in flow: ``GET /api/auth/login`` followed by ``GET /api/auth/callback``.

These tests swap in the fake identity provider (A3), so they never call 42.
In CI ``AUTH_FAKE_PROVIDER_ENABLED`` is off: without the swap, the real
provider would be used.
"""

from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.cookies import ACCESS_COOKIE, REFRESH_COOKIE
from app.api.dependencies import get_provider
from app.config import get_settings
from app.database.models.oauth_states import OAuthState
from app.database.models.users import User
from app.services.identity_provider import FakeIdentityProvider
from tests.api.helpers import set_cookies

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

    expected = FakeIdentityProvider().identity_from_code("fake_code")
    user = db.scalar(select(User).where(User.intra_id == expected.intra_id))
    assert user is not None
    assert user.login == expected.login
    assert user.campus_name == expected.campus_name
    # A state works once: the callback deletes it.
    assert _saved_state(db, state) is None
