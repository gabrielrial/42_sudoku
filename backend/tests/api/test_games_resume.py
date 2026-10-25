"""``GET /api/games/{id}``: resuming a game (``API.md``; ``GAME_RULES.md`` §3).

Authorisation is the point of half of these tests: a valid session of user A
must never reach user B's game, and must not even learn that it exists.
"""

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import clock
from app.database.models.game_sessions import GameSession
from app.database.models.users import User
from tests.api.games import GAMES, GIVENS, NOW, SOLUTION, other_user, start
from tests.api.helpers import error_code, sign_in

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fixed_clock", "week")]

BERLIN_25TH_0010 = datetime(2026, 10, 24, 22, 10, tzinfo=clock.UTC)  # 00:10 on the 25th
BERLIN_25TH_0900 = datetime(2026, 10, 25, 8, 0, tzinfo=clock.UTC)  # 09:00 CET on the 25th


def _game(client: TestClient, difficulty: str = "hard") -> str:
    game_id = start(client, difficulty).json()["game_id"]
    assert isinstance(game_id, str)
    return game_id


def _stored(db: Session, game_id: str) -> GameSession:
    db.expire_all()
    game = db.get(GameSession, uuid.UUID(game_id))
    assert game is not None
    return game


# --- the owner -------------------------------------------------------------------------------


def test_the_owner_gets_everything_to_rebuild_the_board(signed_in: TestClient) -> None:
    game_id = _game(signed_in)

    response = signed_in.get(f"{GAMES}/{game_id}")

    assert response.status_code == 200
    assert response.json() == {
        "game_id": game_id,
        "difficulty": "hard",
        "date": "2026-10-24",
        "givens": GIVENS,
        "state": GIVENS,
        "status": "in_progress",
        "started_at": NOW.isoformat().replace("+00:00", "Z"),
        "completed_at": None,
        "official_seconds": None,
        "active_seconds": 0,
        "submission_count": 0,
    }


def test_the_state_is_the_servers_not_the_clients(db: Session, signed_in: TestClient) -> None:
    # Resuming restores what the server stored (GAME_RULES.md §3), whatever the
    # client remembers.
    game_id = _game(signed_in)
    game = _stored(db, game_id)
    first_empty = GIVENS.index("0")
    game.state = GIVENS[:first_empty] + "7" + GIVENS[first_empty + 1 :]
    db.commit()

    body = signed_in.get(f"{GAMES}/{game_id}").json()

    assert body["state"][first_empty] == "7"
    assert body["givens"] == GIVENS  # the givens are the puzzle's, never the state's


def test_resuming_never_reveals_the_solution(signed_in: TestClient) -> None:
    assert SOLUTION not in signed_in.get(f"{GAMES}/{_game(signed_in)}").text


def test_reading_is_not_activity(db: Session, signed_in: TestClient, fixed_clock: Callable) -> None:
    # Only inputs and heartbeats keep a game alive; looking at it does not.
    game_id = _game(signed_in)
    fixed_clock(NOW + timedelta(minutes=20))

    signed_in.get(f"{GAMES}/{game_id}")

    assert _stored(db, game_id).last_activity_at == NOW


# --- anyone else: 404, never 403 ---------------------------------------------------------------


def test_another_users_game_is_404(db: Session, db_client: TestClient, user: User) -> None:
    sign_in(db_client, db, user)
    game_id = _game(db_client)

    sign_in(db_client, db, other_user(db))
    response = db_client.get(f"{GAMES}/{game_id}")

    assert response.status_code == 404
    assert error_code(response) == "game_not_found"


def test_someone_elses_game_and_no_game_look_the_same(
    db: Session, db_client: TestClient, user: User
) -> None:
    # A 403, or any difference at all, would confirm the game exists.
    sign_in(db_client, db, user)
    game_id = _game(db_client)
    sign_in(db_client, db, other_user(db))

    theirs = db_client.get(f"{GAMES}/{game_id}")
    nobodys = db_client.get(f"{GAMES}/{uuid.uuid4()}")

    assert theirs.status_code == nobodys.status_code == 404
    assert theirs.json() == nobodys.json()


@pytest.mark.parametrize("bad_id", ["not-a-uuid", "1", "' OR 1=1 --", "%00"])
def test_a_malformed_id_is_404_too(signed_in: TestClient, bad_id: str) -> None:
    response = signed_in.get(f"{GAMES}/{bad_id}")

    assert response.status_code == 404
    assert error_code(response) == "game_not_found"


def test_without_a_session_it_is_401(db_client: TestClient) -> None:
    assert db_client.get(f"{GAMES}/{uuid.uuid4()}").status_code == 401


# --- after midnight --------------------------------------------------------------------------


def test_a_game_left_overnight_is_410(signed_in: TestClient, fixed_clock: Callable) -> None:
    # Started 23:30 on the 24th, left; back at 09:00 on the 25th.
    game_id = _game(signed_in)
    fixed_clock(BERLIN_25TH_0900)

    response = signed_in.get(f"{GAMES}/{game_id}")

    assert response.status_code == 410
    assert error_code(response) == "game_closed"


def test_a_game_still_played_after_midnight_resumes(
    db: Session, signed_in: TestClient, fixed_clock: Callable
) -> None:
    game_id = _game(signed_in)
    game = _stored(db, game_id)
    game.last_activity_at = BERLIN_25TH_0010 - timedelta(minutes=1)  # an input at 00:09
    db.commit()
    fixed_clock(BERLIN_25TH_0010)

    body = signed_in.get(f"{GAMES}/{game_id}").json()

    assert body["status"] == "in_progress"
    assert body["date"] == "2026-10-24"  # still the 24th's game (D7)


def test_a_completed_game_never_closes(
    db: Session, signed_in: TestClient, fixed_clock: Callable
) -> None:
    game_id = _game(signed_in)
    game = _stored(db, game_id)
    game.completed_at = NOW + timedelta(minutes=19, seconds=47)
    db.commit()
    fixed_clock(NOW + timedelta(days=7))

    body = signed_in.get(f"{GAMES}/{game_id}").json()

    assert body["status"] == "completed"
    assert body["official_seconds"] == 19 * 60 + 47
