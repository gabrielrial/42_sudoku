"""Origin check: state-changing requests must come from the front end's origin.

``SameSite=Lax`` already keeps cookies off cross-site POSTs; this is the second
layer that ``API.md`` asks for. Safe methods (GET, HEAD, OPTIONS) are not checked.

The test clients send the right ``Origin`` by default (``tests/conftest.py``);
these tests remove or replace it.
"""

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.models.refresh_tokens import RefreshToken
from app.database.models.users import User
from tests.api.helpers import PASSWORD, set_cookies, sign_in

pytestmark = pytest.mark.db

FRONTEND = get_settings().frontend_origin

LOGIN = "/api/users/login"
SIGNUP = "/api/users/signup"
REFRESH = "/api/auth/refresh"
LOGOUT = "/api/auth/logout"
ME = "/api/users/me"

BAD_ORIGINS = [
    "https://evil.example",
    "null",  # sandboxed iframes, file:// pages, some redirects
    FRONTEND + "/",  # exact match only, no normalising
    FRONTEND + ".evil.example",  # prefix of a hostile host
    FRONTEND.replace("http://", "https://", 1),  # other scheme
    FRONTEND.upper(),
]


def _post(client: TestClient, path: str, origin: str | None) -> Response:
    """POST with exactly this ``Origin`` (``None``: no header at all)."""
    if origin is None:
        client.headers.pop("origin", None)
        return client.post(path)
    return client.post(path, headers={"Origin": origin})


def _assert_forbidden(response: Response) -> None:
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_origin"
    assert set_cookies(response) == {}


# --- rejected ----------------------------------------------------------------


@pytest.mark.parametrize("path", [LOGIN, SIGNUP, REFRESH, LOGOUT])
def test_a_post_without_origin_is_403(db_client: TestClient, path: str) -> None:
    _assert_forbidden(_post(db_client, path, None))


@pytest.mark.parametrize("origin", BAD_ORIGINS)
@pytest.mark.parametrize("path", [LOGIN, SIGNUP, REFRESH, LOGOUT])
def test_a_post_from_another_origin_is_403(db_client: TestClient, path: str, origin: str) -> None:
    _assert_forbidden(_post(db_client, path, origin))


# --- nothing happens when rejected --------------------------------------------
# The check runs before the endpoint: no user, no session, no revocation.


def test_a_rejected_login_logs_nobody_in(db: Session, db_client: TestClient, ana: User) -> None:
    response = db_client.post(
        LOGIN,
        data={"username": "ana", "password": PASSWORD},
        headers={"Origin": "https://evil.example"},
    )

    _assert_forbidden(response)
    assert db.query(RefreshToken).count() == 0


def test_a_rejected_signup_creates_nobody(db: Session, db_client: TestClient) -> None:
    response = db_client.post(
        SIGNUP,
        json={"username": "mallory", "password": PASSWORD},
        headers={"Origin": "https://evil.example"},
    )

    _assert_forbidden(response)
    assert db.query(User).count() == 0


def test_a_rejected_logout_keeps_the_session(db: Session, db_client: TestClient, ana: User) -> None:
    sign_in(db_client, db, ana)

    _assert_forbidden(_post(db_client, LOGOUT, "https://evil.example"))

    # The refresh token was not revoked: it still rotates from the real origin.
    assert db_client.post(REFRESH).status_code == 200


# --- allowed -----------------------------------------------------------------


def test_the_front_end_origin_is_allowed(db: Session, db_client: TestClient, ana: User) -> None:
    sign_in(db_client, db, ana)

    response = db_client.post(REFRESH, headers={"Origin": FRONTEND})

    assert response.status_code == 200


def test_a_get_needs_no_origin(db: Session, db_client: TestClient, ana: User) -> None:
    sign_in(db_client, db, ana)
    db_client.headers.pop("origin", None)

    assert db_client.get(ME).status_code == 200


def test_health_needs_no_origin(client: TestClient) -> None:
    client.headers.pop("origin", None)

    assert client.get("/api/health").status_code == 200
