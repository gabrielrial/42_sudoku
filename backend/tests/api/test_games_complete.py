"""``POST /api/games/{id}/complete``: the one place the solution is read (``API.md``; D13).

One boolean, never which cells; every full-grid submission counted (D22); the
grid checked is the server's, not anything the request carries; idempotent once
correct; rate-limited, because this is the brute-force path.

Grids are written straight into ``game_sessions.state``: filling 55 cells
through the input endpoint would only test that endpoint again.
"""

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.database.models.game_sessions import GameSession
from app.database.models.users import User
from app.services.rate_limit import RateLimiter
from tests.api.games import GAMES, GIVENS, NOW, SOLUTION, other_user, start
from tests.api.helpers import error_code, sign_in

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fixed_clock", "week")]

EMPTY = [i for i, ch in enumerate(GIVENS) if ch == "0"]


def _wrong(cells: int = 1) -> str:
    """The solution with ``cells`` of the player's cells wrong (never a given)."""
    grid = list(SOLUTION)
    for i in EMPTY[:cells]:
        grid[i] = "1" if grid[i] != "1" else "2"
    return "".join(grid)


@pytest.fixture
def game_id(signed_in: TestClient) -> str:
    value = start(signed_in, "hard").json()["game_id"]
    assert isinstance(value, str)
    return value


def _stored(db: Session, game_id: str) -> GameSession:
    db.expire_all()
    game = db.get(GameSession, uuid.UUID(game_id))
    assert game is not None
    return game


def _set_state(db: Session, game_id: str, state: str) -> None:
    game = _stored(db, game_id)
    game.state = state
    db.commit()


def _complete(client: TestClient, game_id: str, **kwargs: object) -> Response:
    return client.post(f"{GAMES}/{game_id}/complete", **kwargs)  # type: ignore[arg-type]


def _at(fixed_clock: Callable[[datetime], None], **delta: float) -> datetime:
    instant = NOW + timedelta(**delta)
    fixed_clock(instant)
    return instant


# --- right ---------------------------------------------------------------------------------


def test_the_right_grid_completes_the_game(
    db: Session, signed_in: TestClient, game_id: str, fixed_clock: Callable[[datetime], None]
) -> None:
    _set_state(db, game_id, SOLUTION)
    finished = _at(fixed_clock, minutes=19, seconds=47)

    response = _complete(signed_in, game_id)

    assert response.status_code == 200
    assert response.json() == {
        "correct": True,
        "official_seconds": 19 * 60 + 47,
        "active_seconds": 0,  # nothing between start and here was close enough to count
        "submission_count": 1,
    }
    assert _stored(db, game_id).completed_at == finished


def test_completion_is_idempotent(
    db: Session, signed_in: TestClient, game_id: str, fixed_clock: Callable[[datetime], None]
) -> None:
    _set_state(db, game_id, SOLUTION)
    _at(fixed_clock, minutes=5)
    first = _complete(signed_in, game_id).json()

    _at(fixed_clock, hours=3)  # long after; the game's day is over, too
    again = _complete(signed_in, game_id)

    assert again.status_code == 200
    assert again.json() == first  # completed_at did not move; nothing was counted
    assert _stored(db, game_id).completed_at == NOW + timedelta(minutes=5)


def test_a_completed_game_shows_completed(db: Session, signed_in: TestClient, game_id: str) -> None:
    _set_state(db, game_id, SOLUTION)
    _complete(signed_in, game_id)

    assert signed_in.get(f"{GAMES}/{game_id}").json()["status"] == "completed"


def test_finished_after_midnight_counts_for_its_own_day(
    db: Session, signed_in: TestClient, game_id: str, fixed_clock: Callable[[datetime], None]
) -> None:
    # Started 23:30 on the 24th; the last input at 00:04; submitted at 00:05.
    _set_state(db, game_id, SOLUTION)
    game = _stored(db, game_id)
    game.last_activity_at = NOW + timedelta(minutes=34)
    db.commit()
    _at(fixed_clock, minutes=35)

    assert _complete(signed_in, game_id).json()["correct"] is True
    assert signed_in.get(f"{GAMES}/{game_id}").json()["date"] == "2026-10-24"  # D7


# --- wrong ---------------------------------------------------------------------------------------


def test_a_wrong_grid_says_only_that_it_is_wrong(
    db: Session, signed_in: TestClient, game_id: str
) -> None:
    _set_state(db, game_id, _wrong())

    response = _complete(signed_in, game_id)

    assert response.status_code == 200
    assert response.json() == {"correct": False, "submission_count": 1}
    game = _stored(db, game_id)
    assert game.completed_at is None  # the game stays open
    assert game.state == _wrong()  # and nothing is "corrected"


def test_one_wrong_cell_and_forty_look_the_same(
    db: Session, signed_in: TestClient, game_id: str
) -> None:
    # How wrong a grid is would be an oracle too.
    _set_state(db, game_id, _wrong(1))
    one = _complete(signed_in, game_id)
    _set_state(db, game_id, _wrong(40))
    forty = _complete(signed_in, game_id)

    assert one.json() == {"correct": False, "submission_count": 1}
    assert forty.json() == {"correct": False, "submission_count": 2}
    assert one.headers.keys() == forty.headers.keys()


def test_a_wrong_grid_never_reveals_the_solution(
    db: Session, signed_in: TestClient, game_id: str
) -> None:
    _set_state(db, game_id, _wrong())

    assert SOLUTION not in _complete(signed_in, game_id).text


def test_every_submission_counts_the_right_one_too(
    db: Session, signed_in: TestClient, game_id: str
) -> None:
    _set_state(db, game_id, _wrong())
    _complete(signed_in, game_id)
    _complete(signed_in, game_id)
    _set_state(db, game_id, SOLUTION)

    assert _complete(signed_in, game_id).json()["submission_count"] == 3  # D22


# --- what is checked: the server's grid -----------------------------------------------------------


def test_an_incomplete_grid_is_not_a_submission(
    db: Session, signed_in: TestClient, game_id: str
) -> None:
    response = _complete(signed_in, game_id)  # the givens only

    assert response.status_code == 409
    assert error_code(response) == "grid_incomplete"
    assert _stored(db, game_id).submission_count == 0


def test_a_grid_sent_with_the_request_is_ignored(
    db: Session, signed_in: TestClient, game_id: str
) -> None:
    # LESSONS.md D: there is no second notion of "the submitted grid".
    response = _complete(signed_in, game_id, json={"state": SOLUTION, "grid": SOLUTION})

    assert response.status_code == 409
    assert error_code(response) == "grid_incomplete"
    assert _stored(db, game_id).completed_at is None


# --- whose game, and is it still open --------------------------------------------------------


def test_someone_elses_game_is_404(db: Session, db_client: TestClient, user: User) -> None:
    sign_in(db_client, db, user)
    game_id = start(db_client).json()["game_id"]
    _set_state(db, game_id, SOLUTION)
    sign_in(db_client, db, other_user(db))

    response = _complete(db_client, game_id)

    assert response.status_code == 404
    assert _stored(db, game_id).completed_at is None


def test_a_closed_game_cannot_be_completed_even_when_right(
    db: Session, signed_in: TestClient, game_id: str, fixed_clock: Callable[[datetime], None]
) -> None:
    # Filled in before midnight, left, submitted the next morning: gone.
    _set_state(db, game_id, SOLUTION)
    _at(fixed_clock, hours=12)

    response = _complete(signed_in, game_id)

    assert response.status_code == 410
    assert _stored(db, game_id).completed_at is None


# --- the brute-force path is rate-limited ---------------------------------------------------------


def _fake_completion_limiter(client: TestClient) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    app.state.completion_limiter = RateLimiter(
        capacity=5, refill_per_second=5 / 60, clock=lambda: 1000.0
    )


def test_five_submissions_a_minute(db: Session, signed_in: TestClient, game_id: str) -> None:
    _fake_completion_limiter(signed_in)
    _set_state(db, game_id, _wrong())
    for _ in range(5):
        assert _complete(signed_in, game_id).status_code == 200

    response = _complete(signed_in, game_id)

    assert response.status_code == 429
    assert response.headers["retry-after"] == "12"
    assert _stored(db, game_id).submission_count == 5  # the refused one was not counted


def test_a_completed_game_answers_without_spending_the_limit(
    db: Session, signed_in: TestClient, game_id: str
) -> None:
    _fake_completion_limiter(signed_in)
    _set_state(db, game_id, SOLUTION)
    for _ in range(10):
        assert _complete(signed_in, game_id).json()["correct"] is True


# --- ROADMAP.md, Phase 5 exit: the whole loop through the API alone --------------------------


def test_the_whole_loop_through_the_api_alone(
    signed_in: TestClient, fixed_clock: Callable[[datetime], None]
) -> None:
    app = signed_in.app
    assert isinstance(app, FastAPI)
    app.state.input_limiter = RateLimiter(capacity=100, refill_per_second=1)
    game_id = start(signed_in, "hard").json()["game_id"]

    # One input every ten seconds, each the right digit; nothing else touches the game.
    for n, cell in enumerate(EMPTY, start=1):
        _at(fixed_clock, seconds=10 * n)
        response = signed_in.put(
            f"{GAMES}/{game_id}/cells/{cell}", json={"value": int(SOLUTION[cell])}
        )
        assert response.status_code == 204
    _at(fixed_clock, seconds=10 * len(EMPTY) + 5)
    assert signed_in.post(f"{GAMES}/{game_id}/heartbeat").status_code == 204
    done = _at(fixed_clock, seconds=10 * len(EMPTY) + 6)

    result = _complete(signed_in, game_id).json()

    elapsed = round((done - NOW).total_seconds())
    assert result == {
        "correct": True,
        "official_seconds": elapsed,
        "active_seconds": elapsed,  # every gap was short: all of it was play
        "submission_count": 1,
    }
    today = {p["difficulty"]: p for p in signed_in.get("/api/puzzles/today").json()["puzzles"]}
    assert today["hard"]["status"] == "completed"
    assert today["hard"]["official_seconds"] == elapsed
