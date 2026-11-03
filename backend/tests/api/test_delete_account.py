"""``DELETE /api/users/me``: the account and everything of theirs, for good (D30)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.cookies import ACCESS_COOKIE, REFRESH_COOKIE
from app.database.models.game_sessions import GameSession
from app.database.models.puzzles import Puzzle, PuzzleSolution
from app.database.models.refresh_tokens import RefreshToken
from app.database.models.users import User
from tests.api.games import other_user, start
from tests.api.helpers import error_code, only_cookies, set_cookies, sign_in

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fixed_clock", "week")]

ME = "/api/users/me"


def _count(db: Session, model: type, **where: object) -> int:
    db.expire_all()
    found = db.scalar(select(func.count()).select_from(model).filter_by(**where))
    assert found is not None
    return found


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
    sign_in(db_client, db, user)
    start(db_client)
    puzzles = _count(db, Puzzle)
    solutions = _count(db, PuzzleSolution)

    db_client.delete(ME)

    assert _count(db, User, id=other_id) == 1
    assert _count(db, GameSession, user_id=other_id) == 1
    assert _count(db, RefreshToken, user_id=other_id) == 1
    assert _count(db, Puzzle) == puzzles  # the puzzles are everyone's
    assert _count(db, PuzzleSolution) == solutions


def test_the_cookies_are_cleared(signed_in: TestClient) -> None:
    cookies = set_cookies(signed_in.delete(ME))

    assert cookies[ACCESS_COOKIE]["max-age"] == "0"
    assert cookies[REFRESH_COOKIE]["max-age"] == "0"


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


def test_signing_in_again_is_a_new_account_with_no_past(
    db: Session, signed_in: TestClient, user: User
) -> None:
    # The accepted consequence (D30): today's puzzle can be started afresh.
    intra_id, login, old_id = user.intra_id, user.login, user.id
    game_id = start(signed_in).json()["game_id"]
    signed_in.delete(ME)

    again = User(intra_id=intra_id, login=login, campus_id=1, campus_name="Berlin")
    db.add(again)
    db.commit()
    sign_in(signed_in, db, again)

    assert again.id != old_id
    second = start(signed_in)
    assert second.status_code == 201
    assert second.json()["game_id"] != game_id
