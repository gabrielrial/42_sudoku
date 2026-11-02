"""``DELETE /api/games/{id}/cells``: clear the grid back to its givens (D27).

Not a restart (D3): the official clock, the submissions and the active time
are left alone. It is an input as far as activity and the rate limit go, and
like every input it never reads the solution.
"""

import uuid
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.database.models.game_sessions import GameSession
from app.database.models.users import User
from app.services.rate_limit import RateLimiter
from tests.api.games import GAMES, GIVENS, NOW, SOLUTION, other_user, start
from tests.api.helpers import error_code, sign_in

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fixed_clock", "week")]

EMPTY = [i for i, ch in enumerate(GIVENS) if ch == "0"]


@pytest.fixture
def game_id(signed_in: TestClient) -> str:
    value = start(signed_in, "hard").json()["game_id"]
    assert isinstance(value, str)
    return value


def _clear(client: TestClient, game_id: str) -> Response:
    return client.delete(f"{GAMES}/{game_id}/cells")


def _put(client: TestClient, game_id: str, index: int, value: int) -> Response:
    return client.put(f"{GAMES}/{game_id}/cells/{index}", json={"value": value})


def _stored(db: Session, game_id: str) -> GameSession:
    db.expire_all()
    game = db.get(GameSession, uuid.UUID(game_id))
    assert game is not None
    return game


def _at(fixed_clock: Callable[[datetime], None], **delta: float) -> datetime:
    instant = NOW + timedelta(**delta)
    fixed_clock(instant)
    return instant


def _filled(db: Session, game_id: str, state: str) -> None:
    game = _stored(db, game_id)
    game.state = state
    db.commit()


# --- what it does ---------------------------------------------------------------------------


def test_every_cell_the_player_filled_is_empty_again(
    db: Session, signed_in: TestClient, game_id: str
) -> None:
    _put(signed_in, game_id, EMPTY[0], 4)
    _put(signed_in, game_id, EMPTY[1], 7)

    response = _clear(signed_in, game_id)

    assert response.status_code == 204
    assert _stored(db, game_id).state == GIVENS
    assert signed_in.get(f"{GAMES}/{game_id}").json()["state"] == GIVENS


def test_the_givens_stay(db: Session, signed_in: TestClient, game_id: str) -> None:
    _filled(db, game_id, SOLUTION)

    _clear(signed_in, game_id)

    state = _stored(db, game_id).state
    assert all(s == g for s, g in zip(state, GIVENS, strict=True) if g != "0")
    assert all(s == "0" for s, g in zip(state, GIVENS, strict=True) if g == "0")


def test_an_empty_grid_clears_too(db: Session, signed_in: TestClient, game_id: str) -> None:
    assert _clear(signed_in, game_id).status_code == 204
    assert _stored(db, game_id).state == GIVENS


# --- not a restart (D3) ----------------------------------------------------------------------


def test_the_clock_and_the_submissions_are_left_alone(
    db: Session, signed_in: TestClient, game_id: str, fixed_clock: Callable[[datetime], None]
) -> None:
    wrong = SOLUTION[:-1] + ("1" if SOLUTION[-1] != "1" else "2")
    _filled(db, game_id, wrong)
    assert signed_in.post(f"{GAMES}/{game_id}/complete").json()["correct"] is False
    started = _stored(db, game_id).started_at
    _at(fixed_clock, minutes=5)

    _clear(signed_in, game_id)

    game = _stored(db, game_id)
    assert game.started_at == started
    assert game.submission_count == 1
    assert game.completed_at is None


def test_it_is_activity_like_an_input(
    db: Session, signed_in: TestClient, game_id: str, fixed_clock: Callable[[datetime], None]
) -> None:
    contact = _at(fixed_clock, seconds=30)

    _clear(signed_in, game_id)

    game = _stored(db, game_id)
    assert game.last_activity_at == contact
    assert game.active_seconds == 30  # a short gap: play, as for any input


def test_the_active_time_already_counted_stays(
    db: Session, signed_in: TestClient, game_id: str, fixed_clock: Callable[[datetime], None]
) -> None:
    _at(fixed_clock, seconds=30)
    _put(signed_in, game_id, EMPTY[0], 4)
    assert _stored(db, game_id).active_seconds == 30
    _at(fixed_clock, seconds=60)

    _clear(signed_in, game_id)

    assert _stored(db, game_id).active_seconds == 60  # added to, never restarted


def test_it_keeps_a_game_alive_past_midnight(
    db: Session, signed_in: TestClient, game_id: str, fixed_clock: Callable[[datetime], None]
) -> None:
    # 23:30 start; a clear at 23:50, a look at 00:00 on the next day.
    _at(fixed_clock, minutes=20)
    _clear(signed_in, game_id)
    _at(fixed_clock, minutes=30)

    assert signed_in.get(f"{GAMES}/{game_id}").json()["status"] == "in_progress"


# --- whose game, and is it still open ---------------------------------------------------------


def test_someone_elses_game_is_404_and_untouched(
    db: Session, db_client: TestClient, user: User
) -> None:
    sign_in(db_client, db, user)
    game_id = start(db_client).json()["game_id"]
    _filled(db, game_id, SOLUTION)
    sign_in(db_client, db, other_user(db))

    response = _clear(db_client, game_id)

    assert response.status_code == 404
    assert _stored(db, game_id).state == SOLUTION


def test_a_completed_game_is_409_and_keeps_its_grid(
    db: Session, signed_in: TestClient, game_id: str
) -> None:
    _filled(db, game_id, SOLUTION)
    assert signed_in.post(f"{GAMES}/{game_id}/complete").json()["correct"] is True

    response = _clear(signed_in, game_id)

    assert response.status_code == 409
    assert error_code(response) == "game_completed"
    assert _stored(db, game_id).state == SOLUTION


def test_a_closed_game_is_410_and_keeps_its_grid(
    db: Session, signed_in: TestClient, game_id: str, fixed_clock: Callable[[datetime], None]
) -> None:
    _filled(db, game_id, SOLUTION)
    _at(fixed_clock, hours=12)  # the next morning

    response = _clear(signed_in, game_id)

    assert response.status_code == 410
    assert _stored(db, game_id).state == SOLUTION


# --- one input, as far as the rate limit goes -------------------------------------------------


def test_it_spends_one_input_from_the_games_budget(signed_in: TestClient, game_id: str) -> None:
    app = signed_in.app
    assert isinstance(app, FastAPI)
    app.state.input_limiter = RateLimiter(capacity=2, refill_per_second=1, clock=lambda: 0.0)

    assert _put(signed_in, game_id, EMPTY[0], 4).status_code == 204
    assert _clear(signed_in, game_id).status_code == 204

    refused = _clear(signed_in, game_id)
    assert refused.status_code == 429
    assert refused.headers["retry-after"] == "1"
    assert _put(signed_in, game_id, EMPTY[0], 4).status_code == 429


def test_a_clear_refused_by_the_limit_leaves_the_grid(
    db: Session, signed_in: TestClient, game_id: str
) -> None:
    app = signed_in.app
    assert isinstance(app, FastAPI)
    app.state.input_limiter = RateLimiter(capacity=1, refill_per_second=1, clock=lambda: 0.0)
    assert _put(signed_in, game_id, EMPTY[0], 4).status_code == 204
    filled = _stored(db, game_id).state

    assert _clear(signed_in, game_id).status_code == 429

    assert _stored(db, game_id).state == filled


# --- the solution ------------------------------------------------------------------------------


@pytest.fixture
def statements(db: Session) -> Iterator[list[str]]:
    seen: list[str] = []

    def record(_conn: object, _cursor: object, statement: str, *_: object) -> None:
        seen.append(statement)

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", record)
    yield seen
    event.remove(connection, "before_cursor_execute", record)


def test_clearing_never_reads_the_solution(
    signed_in: TestClient, game_id: str, statements: list[str]
) -> None:
    _clear(signed_in, game_id)

    assert statements, "the listener saw nothing: the test would pass vacuously"
    assert not [s for s in statements if "puzzle_solutions" in s]
