"""``GET /api/users/me``, ``POST /api/auth/refresh`` and ``POST /api/auth/logout``.

The test client keeps cookies like a browser: what the server sets is sent back
on later requests whose path matches. ``only_cookies`` replaces the jar when a
test needs to send something specific (an old token, garbage, nothing).
"""

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.database.models.users import User
from tests.api.helpers import error_code, only_cookies, set_cookies, sign_in

pytestmark = pytest.mark.db

ME = "/api/users/me"
REFRESH = "/api/auth/refresh"
LOGOUT = "/api/auth/logout"


def _assert_not_authenticated(response: Response) -> None:
    """401 with the code that sends the front end to the login page.

    Every way of not having a session answers the same code: the client must not
    learn whether a refresh token was unknown, expired or reused (theft).
    """
    assert response.status_code == 401
    assert error_code(response) == "not_authenticated"


# --- /me ---------------------------------------------------------------------


def test_me_without_a_cookie_is_401(db_client: TestClient) -> None:
    _assert_not_authenticated(db_client.get(ME))


def test_me_with_a_made_up_token_is_401(db_client: TestClient) -> None:
    only_cookies(db_client, access_token="not-a-token")

    _assert_not_authenticated(db_client.get(ME))


def test_me_with_a_session_returns_the_user(db: Session, db_client: TestClient, user: User) -> None:
    sign_in(db_client, db, user)

    response = db_client.get(ME)

    assert response.status_code == 200
    assert response.json() == {"login": "ana", "campus_name": "Berlin"}


# --- /refresh ----------------------------------------------------------------


def test_refresh_without_a_cookie_is_401(db_client: TestClient) -> None:
    _assert_not_authenticated(db_client.post(REFRESH))


def test_refresh_with_a_made_up_token_is_401(db_client: TestClient) -> None:
    only_cookies(db_client, refresh_token="not-a-token")

    _assert_not_authenticated(db_client.post(REFRESH))


def test_refresh_returns_the_user_and_new_cookies(
    db: Session, db_client: TestClient, user: User
) -> None:
    old = sign_in(db_client, db, user)

    response = db_client.post(REFRESH)

    assert response.status_code == 200
    assert response.json() == {"login": "ana", "campus_name": "Berlin"}
    new = set_cookies(response)
    assert new["refresh_token"]["value"] != old["refresh_token"]
    assert new["access_token"]["value"]  # a fresh access token is set too


def test_refresh_alone_is_enough_to_get_back_in(
    db: Session, db_client: TestClient, user: User
) -> None:
    # The access cookie has expired and the browser dropped it: only the refresh one is left.
    tokens = sign_in(db_client, db, user)
    only_cookies(db_client, refresh_token=tokens["refresh_token"])
    _assert_not_authenticated(db_client.get(ME))

    assert db_client.post(REFRESH).status_code == 200

    assert db_client.get(ME).status_code == 200  # with the access cookie /refresh just set


def test_reusing_an_old_refresh_token_logs_the_device_out(
    db: Session, db_client: TestClient, user: User
) -> None:
    old = sign_in(db_client, db, user)["refresh_token"]
    new = set_cookies(db_client.post(REFRESH))["refresh_token"]["value"]

    only_cookies(db_client, refresh_token=old)  # somebody replays the old token
    _assert_not_authenticated(db_client.post(REFRESH))

    only_cookies(db_client, refresh_token=new)  # and the legitimate one is revoked with it
    _assert_not_authenticated(db_client.post(REFRESH))


# --- /logout -----------------------------------------------------------------


def test_logout_answers_204(db: Session, db_client: TestClient, user: User) -> None:
    sign_in(db_client, db, user)

    response = db_client.post(LOGOUT)

    assert response.status_code == 204
    assert response.content == b""


def test_logout_clears_both_cookies_on_their_own_paths(
    db: Session, db_client: TestClient, user: User
) -> None:
    sign_in(db_client, db, user)

    cookies = set_cookies(db_client.post(LOGOUT))

    # A cookie is only deleted when name *and* path match the ones it was set with.
    assert cookies["access_token"]["max-age"] == "0"
    assert cookies["access_token"]["path"] == "/"
    assert cookies["refresh_token"]["max-age"] == "0"
    assert cookies["refresh_token"]["path"] == "/api/auth"


def test_after_logout_the_refresh_token_no_longer_works(
    db: Session, db_client: TestClient, user: User
) -> None:
    refresh_token = sign_in(db_client, db, user)["refresh_token"]

    db_client.post(LOGOUT)

    only_cookies(db_client, refresh_token=refresh_token)  # even if somebody kept a copy
    _assert_not_authenticated(db_client.post(REFRESH))


def test_logout_without_a_cookie_is_still_204(db_client: TestClient) -> None:
    assert db_client.post(LOGOUT).status_code == 204


def test_logout_with_a_made_up_token_is_still_204(db_client: TestClient) -> None:
    only_cookies(db_client, refresh_token="not-a-token")

    assert db_client.post(LOGOUT).status_code == 204
