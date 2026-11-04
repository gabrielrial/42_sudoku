"""``DELETE /api/users/me``: the account and everything of theirs, for good (D30)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.api.cookies import ACCESS_COOKIE, ACCESS_PATH, REFRESH_COOKIE, REFRESH_PATH
from app.api.dependencies import get_provider
from app.api.routers import auth as auth_router
from app.database.models.game_sessions import GameSession
from app.database.models.puzzles import Puzzle, PuzzleSolution
from app.database.models.refresh_tokens import RefreshToken
from app.database.models.users import User
from app.services.identity_provider import FakeIdentityProvider
from app.services.refresh_token import issue_refresh_token
from app.services.users import delete_user
from tests.api.games import other_user, start
from tests.api.helpers import error_code, only_cookies, set_cookies, sign_in

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fixed_clock", "week")]

ME = "/api/users/me"


def _count(db: Session, model: type, **where: object) -> int:
    db.expire_all()
    found = db.scalar(select(func.count()).select_from(model).filter_by(**where))
    assert found is not None
    return found


def _through_the_callback(client: TestClient, login: str) -> Response:
    """A real sign-in, as far as the application can tell: /login, then its callback."""
    app = client.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_provider] = lambda: FakeIdentityProvider(login)
    client.cookies.clear()
    to_42 = client.get("/api/auth/login", follow_redirects=False)
    return client.get(to_42.headers["location"], follow_redirects=False)


def test_the_deletion_is_committed(db_engine: Engine) -> None:
    # Every other test here shares one transaction with the endpoint, so they
    # cannot tell a commit from a flush. Real sessions, seen from another one.
    with Session(db_engine) as setup:
        user = User(intra_id=4242, login="really-gone", campus_id=1, campus_name="Berlin")
        setup.add(user)
        setup.commit()
        user_id = user.id
        issue_refresh_token(setup, user_id)
        setup.commit()
    try:
        with Session(db_engine) as session:
            found = session.get(User, user_id)
            assert found is not None
            delete_user(session, found)

        with Session(db_engine) as observer:
            assert observer.get(User, user_id) is None
            count = select(func.count()).select_from(RefreshToken).filter_by(user_id=user_id)
            assert observer.scalar(count) == 0
    finally:
        with Session(db_engine) as cleanup:
            cleanup.execute(delete(User).where(User.id == user_id))
            cleanup.commit()


def test_the_user_their_games_and_their_sessions_are_gone(
    db: Session, signed_in: TestClient, user: User
) -> None:
    user_id = user.id
    assert start(signed_in, "easy").status_code == 201
    assert start(signed_in, "hard").status_code == 201
    assert _count(db, RefreshToken, user_id=user_id) == 1

    response = signed_in.delete(ME)

    assert response.status_code == 204
    assert _count(db, User, id=user_id) == 0
    assert _count(db, GameSession, user_id=user_id) == 0
    assert _count(db, RefreshToken, user_id=user_id) == 0


def test_nobody_elses_data_is_touched(db: Session, db_client: TestClient, user: User) -> None:
    other = other_user(db)
    other_id = other.id
    sign_in(db_client, db, other)
    start(db_client)
    user_id = user.id
    sign_in(db_client, db, user)
    start(db_client)
    puzzles = _count(db, Puzzle)
    solutions = _count(db, PuzzleSolution)

    assert db_client.delete(ME).status_code == 204

    assert _count(db, User, id=user_id) == 0  # the caller's did go
    assert _count(db, User, id=other_id) == 1
    assert _count(db, GameSession, user_id=other_id) == 1
    assert _count(db, RefreshToken, user_id=other_id) == 1
    assert _count(db, Puzzle) == puzzles  # the puzzles are everyone's
    assert _count(db, PuzzleSolution) == solutions


def test_the_cookies_are_cleared(db: Session, signed_in: TestClient, user: User) -> None:
    user_id = user.id

    cookies = set_cookies(signed_in.delete(ME))

    assert _count(db, User, id=user_id) == 0
    assert cookies[ACCESS_COOKIE]["max-age"] == "0"
    assert cookies[REFRESH_COOKIE]["max-age"] == "0"
    # A cookie is only deleted when name *and* path match the ones it was set with.
    assert cookies[ACCESS_COOKIE]["path"] == ACCESS_PATH
    assert cookies[REFRESH_COOKIE]["path"] == REFRESH_PATH


def test_tokens_issued_before_are_refused_afterwards(
    db: Session, db_client: TestClient, user: User
) -> None:
    tokens = sign_in(db_client, db, user)

    db_client.delete(ME)

    only_cookies(db_client, **tokens)
    assert db_client.get(ME).status_code == 401
    assert db_client.post("/api/auth/refresh").status_code == 401


def test_every_device_is_signed_out(db: Session, db_client: TestClient, user: User) -> None:
    other_device = sign_in(db_client, db, user)
    sign_in(db_client, db, user)

    db_client.delete(ME)

    only_cookies(db_client, **other_device)
    assert db_client.post("/api/auth/refresh").status_code == 401


def test_nobody_signed_in_is_401(db: Session, db_client: TestClient, user: User) -> None:
    db_client.cookies.clear()

    response = db_client.delete(ME)

    assert response.status_code == 401
    assert error_code(response) == "not_authenticated"
    assert _count(db, User, id=user.id) == 1


def test_another_origin_is_refused(db: Session, signed_in: TestClient, user: User) -> None:
    response = signed_in.delete(ME, headers={"Origin": "https://evil.example"})

    assert response.status_code == 403
    assert _count(db, User, id=user.id) == 1


def test_signing_in_again_is_a_new_account_with_no_past(db: Session, db_client: TestClient) -> None:
    # The accepted consequence (D30): today's puzzle can be started afresh.
    assert _through_the_callback(db_client, "ana").headers["location"].count("login_error") == 0
    game_id = start(db_client).json()["game_id"]
    old_id = db.scalar(select(User.id).where(User.login == "ana"))
    assert db_client.delete(ME).status_code == 204

    response = _through_the_callback(db_client, "ana")

    assert "login_error" not in response.headers["location"]
    assert db_client.get(ME).json()["login"] == "ana"
    assert db.scalar(select(User.id).where(User.login == "ana")) != old_id
    second = start(db_client)
    assert second.status_code == 201
    assert second.json()["game_id"] != game_id


@pytest.mark.parametrize(
    "conflict",
    [
        IntegrityError("INSERT", {}, Exception("foreign key")),  # deleted before the token insert
        StaleDataError("the row was gone"),  # deleted before the login's update
    ],
)
def test_a_deletion_during_a_sign_in_is_a_redirect_not_a_500(
    db_client: TestClient, monkeypatch: pytest.MonkeyPatch, conflict: Exception
) -> None:
    def deleted_meanwhile(*_: object) -> str:
        raise conflict

    monkeypatch.setattr(auth_router, "issue_refresh_token", deleted_meanwhile)

    response = _through_the_callback(db_client, "ana")

    assert response.status_code == 302
    assert response.headers["location"].endswith("/?login_error=sign_in_conflict")
    assert ACCESS_COOKIE not in set_cookies(response)
