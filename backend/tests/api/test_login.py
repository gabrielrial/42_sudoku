"""``POST /api/users/login``: checks the password and sets the two auth cookies."""

import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routers import users as users_router
from app.config import get_settings
from app.database.models.refresh_tokens import RefreshToken
from app.database.models.users import User
from app.database.schema.user import PASSWORD_MAX_LENGTH
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


@pytest.mark.parametrize("username", ["Ana", "ANA", "aNa"])
def test_login_ignores_the_case_of_the_username(
    db_client: TestClient, ana: User, username: str
) -> None:
    # Usernames are stored in lower case (see UserCreate); the login lowers
    # what it is given in the same way.
    response = _login(db_client, username, PASSWORD)

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


def test_the_password_is_case_sensitive(db_client: TestClient, ana: User) -> None:
    response = _login(db_client, "ana", PASSWORD.upper())

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


# --- password length ---------------------------------------------------------
# argon2 hashes the whole password, so the login refuses long ones before
# hashing anything: otherwise anybody could keep the CPU busy without an account.


def _spy_on_verify_password(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace the login's ``verify_password``; return the passwords it receives."""
    received: list[str] = []

    def spy(password: str, password_hash: str) -> bool:
        received.append(password)
        return False

    monkeypatch.setattr(users_router, "verify_password", spy)
    return received


@pytest.mark.parametrize("username", ["ana", "nobody"])
def test_a_password_over_the_limit_is_401_without_hashing(
    db_client: TestClient, ana: User, monkeypatch: pytest.MonkeyPatch, username: str
) -> None:
    received = _spy_on_verify_password(monkeypatch)

    response = _login(db_client, username, "x" * (PASSWORD_MAX_LENGTH + 1))

    assert response.status_code == 401
    assert _cookies(response) == {}
    assert received == []


def test_a_password_at_the_limit_is_still_checked(
    db_client: TestClient, ana: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    received = _spy_on_verify_password(monkeypatch)
    password = "x" * PASSWORD_MAX_LENGTH

    response = _login(db_client, "ana", password)

    assert response.status_code == 401  # wrong password, but it was hashed
    assert received == [password]
