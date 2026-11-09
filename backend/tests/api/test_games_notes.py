"""``PUT /api/games/{id}/notes/{index}``: the player's notes (D33).

Candidates the player writes in an empty cell. Part of the game the server
holds, legal like a digit, never judged. Placing a digit clears its cell's notes
and takes that digit out of the notes of its row, column and box.
"""

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.game_moves import GameMove
from app.database.models.game_sessions import GameSession
from app.database.models.users import User
from app.services.rate_limit import RateLimiter
from sudoku.board import PEERS
from tests.api.games import GAMES, GIVENS, NOW, SOLUTION, other_user, start
from tests.api.helpers import error_code, sign_in

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fixed_clock", "week")]

EMPTY = [i for i, ch in enumerate(GIVENS) if ch == "0"]
A_GIVEN = GIVENS.index(next(ch for ch in GIVENS if ch != "0"))
CELL = EMPTY[0]
EMPTY_PEER = next(c for c in EMPTY if c in PEERS[CELL])
NOT_A_PEER = next(c for c in EMPTY if c != CELL and c not in PEERS[CELL])


@pytest.fixture
def game_id(signed_in: TestClient) -> str:
    value = start(signed_in, "hard").json()["game_id"]
    assert isinstance(value, str)
    return value


def _notes(client: TestClient, game_id: str, index: int, notes: object) -> Response:
    return client.put(f"{GAMES}/{game_id}/notes/{index}", json={"notes": notes})


def _digit(client: TestClient, game_id: str, index: int, value: int | None) -> Response:
    return client.put(f"{GAMES}/{game_id}/cells/{index}", json={"value": value})


def _shown(client: TestClient, game_id: str) -> list[list[int]]:
    notes = client.get(f"{GAMES}/{game_id}").json()["notes"]
    assert isinstance(notes, list)
    return notes


def _stored(db: Session, game_id: str) -> GameSession:
    db.expire_all()
    game = db.get(GameSession, uuid.UUID(game_id))
    assert game is not None
    return game


# --- writing and reading -----------------------------------------------------------------


def test_a_new_game_has_no_notes(signed_in: TestClient) -> None:
    started = start(signed_in, "easy").json()

    assert started["notes"] == [[]] * 81


def test_notes_are_saved_and_shown_on_resume(signed_in: TestClient, game_id: str) -> None:
    assert _notes(signed_in, game_id, CELL, [7, 1, 4]).status_code == 204

    notes = _shown(signed_in, game_id)
    assert notes[CELL] == [1, 4, 7]  # ascending, whatever order they came in
    assert all(n == [] for i, n in enumerate(notes) if i != CELL)


def test_writing_notes_replaces_them_and_empty_removes_them(
    signed_in: TestClient, game_id: str
) -> None:
    _notes(signed_in, game_id, CELL, [1, 2])
    _notes(signed_in, game_id, CELL, [9])
    assert _shown(signed_in, game_id)[CELL] == [9]

    _notes(signed_in, game_id, CELL, [])
    assert _shown(signed_in, game_id)[CELL] == []


def test_the_database_keeps_one_bitmask_per_cell(
    db: Session, signed_in: TestClient, game_id: str
) -> None:
    _notes(signed_in, game_id, CELL, [1, 9])

    assert _stored(db, game_id).notes[CELL] == 0b100000001


def test_notes_are_activity_like_an_input(
    db: Session, signed_in: TestClient, game_id: str, fixed_clock: Callable[[datetime], None]
) -> None:
    fixed_clock(NOW + timedelta(seconds=30))

    _notes(signed_in, game_id, CELL, [5])

    game = _stored(db, game_id)
    assert game.last_activity_at == NOW + timedelta(seconds=30)
    assert game.active_seconds == 30


# --- placing a digit (GAME_RULES.md §3) --------------------------------------------------


def test_placing_a_digit_clears_its_cell_and_its_peers_of_that_digit(
    signed_in: TestClient, game_id: str
) -> None:
    _notes(signed_in, game_id, CELL, [4, 5])
    _notes(signed_in, game_id, EMPTY_PEER, [4, 6])
    _notes(signed_in, game_id, NOT_A_PEER, [4, 6])

    assert _digit(signed_in, game_id, CELL, 4).status_code == 204

    notes = _shown(signed_in, game_id)
    assert notes[CELL] == []
    assert notes[EMPTY_PEER] == [6]  # the 4 went; the rest stays
    assert notes[NOT_A_PEER] == [4, 6]  # not in its row, column or box


@pytest.mark.parametrize("unit", ["row", "column", "box"])
def test_every_unit_of_the_cell_loses_the_digit(
    signed_in: TestClient, game_id: str, unit: str
) -> None:
    row, col, box = CELL // 9, CELL % 9, (CELL // 27) * 3 + (CELL % 9) // 3
    same: dict[str, Callable[[int], bool]] = {
        "row": lambda c: c // 9 == row and c != CELL,
        "column": lambda c: c % 9 == col and c != CELL,
        "box": lambda c: (c // 27) * 3 + (c % 9) // 3 == box and c != CELL,
    }
    peer = next(c for c in EMPTY if same[unit](c))
    _notes(signed_in, game_id, peer, [3])

    _digit(signed_in, game_id, CELL, 3)

    assert _shown(signed_in, game_id)[peer] == []


def test_emptying_the_cell_brings_no_note_back(signed_in: TestClient, game_id: str) -> None:
    _notes(signed_in, game_id, CELL, [4, 5])
    _notes(signed_in, game_id, EMPTY_PEER, [4])
    _digit(signed_in, game_id, CELL, 4)

    _digit(signed_in, game_id, CELL, None)

    notes = _shown(signed_in, game_id)
    assert notes[CELL] == []
    assert notes[EMPTY_PEER] == []


def test_clearing_the_grid_removes_every_note(signed_in: TestClient, game_id: str) -> None:
    _notes(signed_in, game_id, CELL, [1])
    _notes(signed_in, game_id, NOT_A_PEER, [2])

    signed_in.delete(f"{GAMES}/{game_id}/cells")

    assert _shown(signed_in, game_id) == [[]] * 81


# --- what is refused ---------------------------------------------------------------------


def test_a_given_takes_no_notes(signed_in: TestClient, game_id: str) -> None:
    response = _notes(signed_in, game_id, A_GIVEN, [1])

    assert response.status_code == 409
    assert error_code(response) == "cell_is_given"


def test_a_filled_cell_takes_no_notes(signed_in: TestClient, game_id: str) -> None:
    _digit(signed_in, game_id, CELL, 4)

    response = _notes(signed_in, game_id, CELL, [1])

    assert response.status_code == 409
    assert error_code(response) == "cell_is_filled"


@pytest.mark.parametrize(
    "notes",
    [[0], [10], [-1], [1, 1], [*range(1, 10), 1], ["1"], [1.0], [True], 5, None, {"1": 1}],
)
def test_anything_but_distinct_digits_1_to_9_is_422(
    signed_in: TestClient, game_id: str, notes: object
) -> None:
    assert _notes(signed_in, game_id, CELL, notes).status_code == 422


def test_all_nine_are_allowed(signed_in: TestClient, game_id: str) -> None:
    assert _notes(signed_in, game_id, CELL, list(range(1, 10))).status_code == 204


@pytest.mark.parametrize("index", ["-1", "81", "x"])
def test_an_index_outside_0_to_80_is_422(signed_in: TestClient, game_id: str, index: str) -> None:
    response = signed_in.put(f"{GAMES}/{game_id}/notes/{index}", json={"notes": [1]})

    assert response.status_code == 422


def test_someone_elses_game_is_404_and_untouched(
    db: Session, db_client: TestClient, user: User
) -> None:
    sign_in(db_client, db, user)
    game_id = start(db_client).json()["game_id"]
    sign_in(db_client, db, other_user(db))

    assert _notes(db_client, game_id, CELL, [1]).status_code == 404

    assert _stored(db, game_id).notes == [0] * 81


def test_a_completed_game_takes_no_notes(db: Session, signed_in: TestClient, game_id: str) -> None:
    game = _stored(db, game_id)
    game.completed_at = NOW
    db.commit()

    response = _notes(signed_in, game_id, CELL, [1])

    assert response.status_code == 409
    assert error_code(response) == "game_completed"


def test_a_closed_game_takes_no_notes(
    signed_in: TestClient, game_id: str, fixed_clock: Callable[[datetime], None]
) -> None:
    fixed_clock(NOW + timedelta(hours=12))  # the next morning

    assert _notes(signed_in, game_id, CELL, [1]).status_code == 410


def test_notes_spend_the_same_budget_as_digits(signed_in: TestClient, game_id: str) -> None:
    app = signed_in.app
    assert isinstance(app, FastAPI)
    app.state.input_limiter = RateLimiter(capacity=2, refill_per_second=1, clock=lambda: 0.0)

    assert _notes(signed_in, game_id, CELL, [1]).status_code == 204
    assert _digit(signed_in, game_id, NOT_A_PEER, 4).status_code == 204

    assert _notes(signed_in, game_id, CELL, [2]).status_code == 429
    assert _digit(signed_in, game_id, NOT_A_PEER, 5).status_code == 429


# --- the record of moves (D31) -----------------------------------------------------------


def test_a_change_of_notes_is_recorded_before_and_after(
    db: Session, signed_in: TestClient, game_id: str
) -> None:
    _notes(signed_in, game_id, CELL, [1, 2])
    _notes(signed_in, game_id, CELL, [2])

    db.expire_all()
    moves = list(
        db.scalars(
            select(GameMove).where(GameMove.game_id == uuid.UUID(game_id)).order_by(GameMove.id)
        )
    )
    assert [(m.kind, m.cell, m.previous_notes, m.notes) for m in moves] == [
        ("notes", CELL, 0, 0b11),
        ("notes", CELL, 0b11, 0b10),
    ]
    assert all(m.correct is None for m in moves)


def test_replaying_the_moves_gives_the_stored_notes(
    db: Session, signed_in: TestClient, game_id: str
) -> None:
    # D31: the record cannot disagree with the game. Pruning is not a row of its
    # own; replaying the input that caused it redoes it.
    from app.services.games import place_digit

    _notes(signed_in, game_id, EMPTY_PEER, [3, 8])
    _notes(signed_in, game_id, NOT_A_PEER, [3])
    _digit(signed_in, game_id, CELL, 3)
    _notes(signed_in, game_id, CELL, [])  # refused: the cell is filled
    _digit(signed_in, game_id, CELL, None)
    _notes(signed_in, game_id, CELL, [2, 7])

    db.expire_all()
    replayed = [0] * 81
    for move in db.scalars(
        select(GameMove).where(GameMove.game_id == uuid.UUID(game_id)).order_by(GameMove.id)
    ):
        if move.kind == "notes":
            assert move.cell is not None and move.previous_notes == replayed[move.cell]
            replayed[move.cell] = move.notes or 0
        elif move.kind == "input" and move.value and move.cell is not None:
            replayed = place_digit(replayed, move.cell, move.value)

    assert replayed == _stored(db, game_id).notes


# --- the solution ------------------------------------------------------------------------


def test_notes_never_read_the_solution(db: Session, signed_in: TestClient, game_id: str) -> None:
    from sqlalchemy import event

    seen: list[str] = []

    def record(_conn: object, _cursor: object, statement: str, *_: object) -> None:
        seen.append(statement)

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", record)
    try:
        _notes(signed_in, game_id, CELL, [int(SOLUTION[CELL])])
    finally:
        event.remove(connection, "before_cursor_execute", record)

    assert seen, "the listener saw nothing: the test would pass vacuously"
    assert not [s for s in seen if "puzzle_solutions" in s]
