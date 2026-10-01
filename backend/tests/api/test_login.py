"""``POST /api/users/login``: checks the password and sets the two auth cookies."""

import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.models.refresh_tokens import RefreshToken
from app.database.models.users import User
from app.services.auth import user_from_access_token
from tests.api.helpers import PASSWORD
from tests.api.helpers import login as _login
from tests.api.helpers import set_cookies as _cookies

pytestmark = pytest.mark.db

settings = get_settings()


# --- success -----------------------------------------------------------------


def test_login_answers_with_the_user_and_no_token(db_client: TestClient, ana: User) -> None:
    response = _login(db_client, "ana", PASSWORD)

    assert response.status_code == 200
    assert response.json() == {"id": ana.id, "username": "ana"}


def test_login_sets_the_access_cookie(db_client: TestClient, ana: User) -> None:
    cookie = _cookies(_login(db_client, "ana", PASSWORD))["access_token"]

    assert "httponly" in cookie
    assert cookie["samesite"].lower() == "lax"
    assert cookie["path"] == "/"
    assert cookie["max-age"] == str(settings.access_token_minutes * 60)
    assert "secure" not in cookie  # plain http in development and tests


def test_login_sets_the_refresh_cookie(db_client: TestClient, ana: User) -> None:
    cookie = _cookies(_login(db_client, "ana", PASSWORD))["refresh_token"]

    assert "httponly" in cookie
    assert cookie["samesite"].lower() == "lax"
    assert cookie["path"] == "/api/auth"  # sent to refresh and logout only
    assert cookie["max-age"] == str(settings.refresh_token_days * 24 * 3600)
    assert "secure" not in cookie


def test_the_access_cookie_holds_a_valid_token_for_the_user(
    db: Session, db_client: TestClient, ana: User
) -> None:
    token = _cookies(_login(db_client, "ana", PASSWORD))["access_token"]["value"]

    assert user_from_access_token(db, token).id == ana.id


def test_the_refresh_cookie_holds_a_token_saved_in_the_database(
    db: Session, db_client: TestClient, ana: User
) -> None:
    raw = _cookies(_login(db_client, "ana", PASSWORD))["refresh_token"]["value"]

    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).one_or_none()
    assert row is not None
    assert row.user_id == ana.id


# --- failure -----------------------------------------------------------------


def test_wrong_password_is_rejected_without_cookies(db_client: TestClient, ana: User) -> None:
    response = _login(db_client, "ana", "not-the-password")

    assert response.status_code == 401
    assert _cookies(response) == {}


def test_unknown_user_is_rejected_without_cookies(db_client: TestClient) -> None:
    response = _login(db_client, "nobody", PASSWORD)

    assert response.status_code == 401
    assert _cookies(response) == {}


def test_the_dummy_hash_password_does_not_log_in_a_missing_user(db_client: TestClient) -> None:
    # For unknown users the login checks the password against DUMMY_HASH, the
    # hash of this string, so that both paths take the same time. The match
    # must not let anybody in.
    response = _login(db_client, "nobody", "timing-equaliser")

    assert response.status_code == 401
    assert _cookies(response) == {}


def test_a_failed_login_saves_no_refresh_token(
    db: Session, db_client: TestClient, ana: User
) -> None:
    _login(db_client, "ana", "not-the-password")

    assert db.query(RefreshToken).count() == 0
