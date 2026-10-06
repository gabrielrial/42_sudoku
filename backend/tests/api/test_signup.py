"""``POST /api/users/signup``: validates the body, stores usernames in lower case."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.api.routers import users as users_router
from app.database.models.users import User
from app.utils.security import verify_password
from tests.api.helpers import PASSWORD, error_code

pytestmark = pytest.mark.db

SIGNUP = "/api/users/signup"


def _signup(client: TestClient, username: Any, password: Any = PASSWORD) -> Response:
    return client.post(SIGNUP, json={"username": username, "password": password})


def _count_users(db: Session) -> int:
    return db.query(User).count()


# --- success -----------------------------------------------------------------


def test_signup_answers_201_with_the_public_user(db: Session, db_client: TestClient) -> None:
    response = _signup(db_client, "ana")

    assert response.status_code == 201
    saved = db.query(User).filter(User.username == "ana").one()
    assert response.json() == {"id": saved.id, "username": "ana"}  # no password, no hash


def test_signup_stores_a_hash_not_the_password(db: Session, db_client: TestClient) -> None:
    _signup(db_client, "ana")

    saved = db.query(User).filter(User.username == "ana").one()
    assert saved.password_hash != PASSWORD
    assert verify_password(PASSWORD, saved.password_hash)


def test_signup_stores_the_username_in_lower_case(db: Session, db_client: TestClient) -> None:
    response = _signup(db_client, "Ana_42")

    assert response.status_code == 201
    assert response.json()["username"] == "ana_42"
    assert db.query(User).filter(User.username == "ana_42").count() == 1


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("abc", PASSWORD),  # shortest username
        ("a" * 32, PASSWORD),  # longest username
        ("a-b_c-1", PASSWORD),  # every allowed kind of character
        ("ana", "x" * 8),  # shortest password
        ("ana", "x" * 128),  # longest password
        ("ana", "pässwörd con espacios 🙂"),  # the password itself is free text
    ],
)
def test_signup_accepts_the_limits(db_client: TestClient, username: str, password: str) -> None:
    assert _signup(db_client, username, password).status_code == 201


def test_the_kelvin_sign_becomes_a_plain_k(db_client: TestClient) -> None:
    # "\N{KELVIN SIGN}".lower() == "k": lower-casing runs before the pattern, so what is
    # stored is plain ASCII. Documents the behaviour; it is harmless.
    response = _signup(db_client, "\N{KELVIN SIGN}ai")

    assert response.status_code == 201
    assert response.json()["username"] == "kai"


# --- 409: taken --------------------------------------------------------------


def test_signup_with_a_taken_username_is_409(db: Session, db_client: TestClient, ana: User) -> None:
    response = _signup(db_client, "ana")

    assert response.status_code == 409
    assert error_code(response) == "username_taken"
    assert _count_users(db) == 1


def test_signup_with_a_taken_username_in_other_case_is_409(
    db: Session, db_client: TestClient, ana: User
) -> None:
    response = _signup(db_client, "ANA")

    assert response.status_code == 409
    assert error_code(response) == "username_taken"
    assert _count_users(db) == 1


def test_a_signup_that_loses_a_race_is_409_not_500(
    db: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Two signups for "ana" at the same time: both check, both find nobody, both
    # insert. The UNIQUE constraint lets only one through; the other must still
    # get a clean 409, not a 500.
    #
    # The race is staged inside one request. hash_password runs after the check
    # and before the insert, so the spy commits the rival "ana" right there.
    real_hash_password = users_router.hash_password

    def the_other_request_wins(password: str) -> str:
        db.add(User(username="ana", password_hash="the-winner"))
        db.commit()
        return real_hash_password(password)

    monkeypatch.setattr(users_router, "hash_password", the_other_request_wins)

    response = _signup(db_client, "ana")

    assert response.status_code == 409
    assert error_code(response) == "username_taken"
    assert db.query(User).filter(User.username == "ana").one().password_hash == "the-winner"


# --- 422: invalid body -------------------------------------------------------


@pytest.mark.parametrize(
    "username",
    [
        "ab",  # too short
        "a" * 33,  # too long
        "",  # empty
        "ana maria",  # space
        " ana",  # leading space: not trimmed, rejected
        "ana!",  # punctuation
        "ana.b",  # dot
        "ñandú",  # non-ASCII letters
        "ana🙂",  # emoji
        "\u0430na",  # Cyrillic U+0430, looks like a Latin a
        "ana\n",  # trailing newline
        123,  # not a string
        None,
    ],
)
def test_signup_rejects_a_bad_username(db: Session, db_client: TestClient, username: Any) -> None:
    response = _signup(db_client, username)

    assert response.status_code == 422
    assert _count_users(db) == 0


@pytest.mark.parametrize(
    "password",
    [
        "x" * 7,  # too short
        "x" * 129,  # too long: argon2 would hash all of it
        "",
        12345678,  # not a string
        None,
    ],
)
def test_signup_rejects_a_bad_password(db: Session, db_client: TestClient, password: Any) -> None:
    response = _signup(db_client, "ana", password)

    assert response.status_code == 422
    assert _count_users(db) == 0


@pytest.mark.parametrize("body", [{}, {"username": "ana"}, {"password": PASSWORD}])
def test_signup_rejects_missing_fields(
    db: Session, db_client: TestClient, body: dict[str, str]
) -> None:
    assert db_client.post(SIGNUP, json=body).status_code == 422
    assert _count_users(db) == 0


def test_the_422_uses_the_common_error_shape(db_client: TestClient) -> None:
    response = _signup(db_client, "ab")

    assert response.json() == {
        "error": {
            "code": "invalid_request",
            "message": "The request body or parameters are invalid.",
        }
    }
