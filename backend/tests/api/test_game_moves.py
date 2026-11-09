"""The record of each player's moves (D31): what is written, and what is not."""

import uuid
from collections.abc import Callable, Iterator
from datetime import date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, delete, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models.game_moves import GameMove
from app.database.models.game_sessions import GameSession
from app.database.models.puzzles import Puzzle
from app.database.models.users import User
from app.services import games as games_service
from app.services.game_status import Status
from app.services.games import OwnedGame, clear_cells, complete, play_cell
from app.services.moves import purge_old_moves
from tests.api.games import GAMES, GIVENS, NOW, SOLUTION, make_puzzle, other_user, start
from tests.api.helpers import sign_in

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fixed_clock", "week")]

EMPTY = [i for i, ch in enumerate(GIVENS) if ch == "0"]
A_GIVEN = next(i for i, ch in enumerate(GIVENS) if ch != "0")


@pytest.fixture
def game_id(signed_in: TestClient) -> str:
    value = start(signed_in, "hard").json()["game_id"]
    assert isinstance(value, str)
    return value


def _put(client: TestClient, game_id: str, index: int, value: int | None) -> Response:
    return client.put(f"{GAMES}/{game_id}/cells/{index}", json={"value": value})


def _moves(db: Session, game_id: str) -> list[GameMove]:
    db.expire_all()
    query = select(GameMove).where(GameMove.game_id == uuid.UUID(game_id)).order_by(GameMove.id)
    return list(db.scalars(query))


def _full(db: Session, game_id: str, state: str) -> None:
    game = db.get(GameSession, uuid.UUID(game_id))
    assert game is not None
    game.state = state
    db.commit()


# --- what is written ---------------------------------------------------------------------


def test_an_input_records_who_where_what_and_when(
    db: Session, signed_in: TestClient, game_id: str, user: User
) -> None:
    assert _put(signed_in, game_id, EMPTY[0], 4).status_code == 204

    moves = _moves(db, game_id)
    assert len(moves) == 1
    move = moves[0]
    assert move.kind == "input"
    assert move.user_id == user.id
    assert (move.cell, move.previous_value, move.value) == (EMPTY[0], 0, 4)
    assert move.played_at == NOW


def test_writing_over_and_emptying_a_cell_keep_what_it_held(
    db: Session, signed_in: TestClient, game_id: str
) -> None:
    _put(signed_in, game_id, EMPTY[0], 4)
    _put(signed_in, game_id, EMPTY[0], 7)
    _put(signed_in, game_id, EMPTY[0], None)

    assert [(m.previous_value, m.value) for m in _moves(db, game_id)] == [(0, 4), (4, 7), (7, 0)]


def test_a_wrong_digit_is_recorded_as_typed_and_not_judged(
    db: Session, signed_in: TestClient, game_id: str
) -> None:
    # GAME_RULES.md §4: never flagged, never an error. This path does not know.
    wrong = 1 if SOLUTION[EMPTY[0]] != "1" else 2

    _put(signed_in, game_id, EMPTY[0], wrong)

    move = _moves(db, game_id)[0]
    assert move.value == wrong
    assert move.correct is None


def test_a_clear_is_recorded(db: Session, signed_in: TestClient, game_id: str) -> None:
    signed_in.delete(f"{GAMES}/{game_id}/cells")

    move = _moves(db, game_id)[0]
    assert move.kind == "clear"
    assert move.cell is None


@pytest.mark.parametrize("correct", [True, False])
def test_a_check_records_its_answer(
    db: Session, signed_in: TestClient, game_id: str, correct: bool
) -> None:
    wrong = SOLUTION[:-1] + ("1" if SOLUTION[-1] != "1" else "2")
    _full(db, game_id, SOLUTION if correct else wrong)

    assert signed_in.post(f"{GAMES}/{game_id}/complete").json()["correct"] is correct

    move = _moves(db, game_id)[0]
    assert move.kind == "check"
    assert move.correct is correct


# --- what is not -------------------------------------------------------------------------


def test_a_refused_input_is_not_a_move(db: Session, signed_in: TestClient, game_id: str) -> None:
    assert _put(signed_in, game_id, A_GIVEN, 4).status_code == 409

    assert _moves(db, game_id) == []


def test_someone_elses_game_records_nothing(db: Session, db_client: TestClient, user: User) -> None:
    sign_in(db_client, db, user)
    game_id = start(db_client).json()["game_id"]
    sign_in(db_client, db, other_user(db))

    assert _put(db_client, game_id, EMPTY[0], 4).status_code == 404

    assert _moves(db, game_id) == []


def test_a_heartbeat_is_not_a_move(db: Session, signed_in: TestClient, game_id: str) -> None:
    assert signed_in.post(f"{GAMES}/{game_id}/heartbeat").status_code == 204

    assert _moves(db, game_id) == []


def test_only_a_real_submission_is_a_check(
    db: Session, signed_in: TestClient, game_id: str
) -> None:
    assert signed_in.post(f"{GAMES}/{game_id}/complete").status_code == 409  # cells are empty
    assert _moves(db, game_id) == []

    _full(db, game_id, SOLUTION)
    signed_in.post(f"{GAMES}/{game_id}/complete")
    signed_in.post(f"{GAMES}/{game_id}/complete")  # idempotent: nothing new happened

    assert len(_moves(db, game_id)) == 1


def test_the_answer_of_an_input_says_nothing_of_the_record(
    signed_in: TestClient, game_id: str
) -> None:
    response = _put(signed_in, game_id, EMPTY[0], 4)

    assert response.status_code == 204
    assert response.content == b""
    assert "moves" not in signed_in.get(f"{GAMES}/{game_id}").json()


# --- the table ---------------------------------------------------------------------------


def test_it_is_indexed_by_user_and_by_game(db: Session) -> None:
    indexes = inspect(db.connection()).get_indexes("game_moves")

    assert {tuple(i["column_names"]) for i in indexes} >= {
        ("user_id", "played_at"),
        ("game_id", "played_at"),
    }


AN_INPUT = {"kind": "input", "cell": 0, "previous_value": 0, "value": 1}


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"kind": "nonsense"}, "game_moves_kind_check"),
        ({"kind": "input"}, "game_moves_input_check"),
        ({"kind": "clear", "cell": 3, "previous_value": 0, "value": 1}, "game_moves_input_check"),
        ({"kind": "check"}, "game_moves_check_check"),
        ({"kind": "notes", "cell": 3}, "game_moves_notes_check"),
        ({"kind": "clear", "cell": 3, "previous_notes": 0, "notes": 1}, "game_moves_notes_check"),
        (
            {"kind": "notes", "cell": 3, "previous_notes": 0, "notes": 512},
            "game_moves_notes_range_check",
        ),
        (
            {"kind": "notes", "cell": 3, "previous_notes": -1, "notes": 0},
            "game_moves_previous_notes_check",
        ),
        ({"kind": "clear", "correct": True}, "game_moves_check_check"),
        ({**AN_INPUT, "cell": 81}, "game_moves_cell_check"),
        ({**AN_INPUT, "cell": -1}, "game_moves_cell_check"),
        ({**AN_INPUT, "previous_value": 10}, "game_moves_previous_value_check"),
        ({**AN_INPUT, "value": 10}, "game_moves_value_check"),
        ({**AN_INPUT, "value": -1}, "game_moves_value_check"),
    ],
)
def test_the_database_refuses_a_nonsense_row(
    db: Session, game_id: str, user: User, fields: dict[str, Any], constraint: str
) -> None:
    db.add(GameMove(game_id=uuid.UUID(game_id), user_id=user.id, played_at=NOW, **fields))

    with pytest.raises(IntegrityError, match=constraint):
        db.flush()
    db.rollback()


# --- retention ---------------------------------------------------------------------------


def _move_at(db: Session, game_id: str, user: User, instant: datetime) -> None:
    db.add(
        GameMove(
            game_id=uuid.UUID(game_id),
            user_id=user.id,
            kind="clear",
            played_at=instant,
        )
    )
    db.commit()


def test_the_purge_deletes_only_what_is_past_the_period(
    db: Session, game_id: str, user: User
) -> None:
    now = NOW + timedelta(days=40)
    _move_at(db, game_id, user, now - timedelta(days=30, seconds=1))  # past it
    kept_edge = now - timedelta(days=30)
    _move_at(db, game_id, user, kept_edge)
    _move_at(db, game_id, user, now)

    assert purge_old_moves(db, now, 30) == 1

    assert [m.played_at for m in _moves(db, game_id)] == [kept_edge, now]


def test_the_purge_leaves_the_game_itself_alone(db: Session, game_id: str, user: User) -> None:
    _move_at(db, game_id, user, NOW)

    purge_old_moves(db, NOW + timedelta(days=31), 30)

    db.expire_all()
    assert db.get(GameSession, uuid.UUID(game_id)) is not None
    assert _moves(db, game_id) == []


def test_the_purge_is_committed(db_engine: Engine) -> None:
    # The tests above share one transaction with the code, so they cannot tell a
    # commit from a flush. Real sessions, seen from another one.
    with Session(db_engine) as setup:
        user = User(intra_id=4343, login="old-moves", campus_id=1, campus_name="Berlin")
        setup.add(user)
        puzzle = make_puzzle(setup, date(2000, 1, 1), "easy")
        setup.flush()
        game = GameSession(user_id=user.id, puzzle_id=puzzle.id, state=GIVENS)
        setup.add(game)
        setup.flush()
        setup.add(GameMove(game_id=game.id, user_id=user.id, kind="clear", played_at=NOW))
        setup.commit()
        user_id, puzzle_id = user.id, puzzle.id
    try:
        with Session(db_engine) as session:
            assert purge_old_moves(session, NOW + timedelta(days=31), 30) == 1

        with Session(db_engine) as observer:
            query = select(GameMove).where(GameMove.user_id == user_id)
            assert list(observer.scalars(query)) == []
    finally:
        with Session(db_engine) as cleanup:
            cleanup.execute(delete(User).where(User.id == user_id))
            cleanup.execute(delete(Puzzle).where(Puzzle.id == puzzle_id))
            cleanup.commit()


# --- a move and its action are one (D31) --------------------------------------------------
# With real sessions: the ``db`` fixture turns ``commit()`` into a savepoint, so
# the tests above could not tell one transaction from two.

GAP = timedelta(seconds=90)


@pytest.fixture
def real_game(db_engine: Engine) -> Iterator[uuid.UUID]:
    """A committed game with its grid full and right, ready for any of the three."""
    with Session(db_engine) as setup:
        user = User(intra_id=4444, login="one-transaction", campus_id=1, campus_name="Berlin")
        setup.add(user)
        puzzle = make_puzzle(setup, date(2000, 1, 2), "easy")
        setup.flush()
        game = GameSession(user_id=user.id, puzzle_id=puzzle.id, state=SOLUTION)
        setup.add(game)
        setup.commit()
        user_id, puzzle_id, game_id = user.id, puzzle.id, game.id
    try:
        yield game_id
    finally:
        with Session(db_engine) as cleanup:
            cleanup.execute(delete(User).where(User.id == user_id))
            cleanup.execute(delete(Puzzle).where(Puzzle.id == puzzle_id))
            cleanup.commit()


def _owned(session: Session, game_id: uuid.UUID) -> OwnedGame:
    game = session.get(GameSession, game_id)
    assert game is not None
    puzzle = session.get(Puzzle, game.puzzle_id)
    assert puzzle is not None
    return OwnedGame(game, puzzle, Status.IN_PROGRESS, NOW)


def _boom(*_: object, **__: object) -> None:
    raise RuntimeError("failed half way")


@pytest.mark.parametrize(
    ("step", "action"),
    [
        # What runs after the move is added, failing: nothing may have been kept.
        ("_touch", lambda db, owned: play_cell(db, owned, EMPTY[0], None, GAP)),
        ("_touch", lambda db, owned: clear_cells(db, owned, GAP)),
        # ``complete`` adds its move last: failing there, its other writes must go.
        ("_move", lambda db, owned: complete(db, owned, GAP)),
    ],
    ids=["input", "clear", "check"],
)
def test_a_move_and_its_action_are_saved_together_or_not_at_all(
    db_engine: Engine,
    real_game: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
    step: str,
    action: Callable[[Session, OwnedGame], object],
) -> None:
    with Session(db_engine) as observer:
        before = observer.get(GameSession, real_game)
        assert before is not None
        state, submissions = before.state, before.submission_count
    monkeypatch.setattr(games_service, step, _boom)

    with Session(db_engine) as session, pytest.raises(RuntimeError, match="half way"):
        action(session, _owned(session, real_game))

    with Session(db_engine) as observer:
        after = observer.get(GameSession, real_game)
        assert after is not None
        assert (after.state, after.submission_count) == (state, submissions)
        moves = select(GameMove).where(GameMove.game_id == real_game)
        assert list(observer.scalars(moves)) == []


@pytest.mark.parametrize(
    ("action", "kind"),
    [
        (lambda db, owned: play_cell(db, owned, EMPTY[0], None, GAP), "input"),
        (lambda db, owned: clear_cells(db, owned, GAP), "clear"),
        (lambda db, owned: complete(db, owned, GAP), "check"),
    ],
    ids=["input", "clear", "check"],
)
def test_the_move_is_committed_with_its_action(
    db_engine: Engine,
    real_game: uuid.UUID,
    action: Callable[[Session, OwnedGame], object],
    kind: str,
) -> None:
    with Session(db_engine) as session:
        action(session, _owned(session, real_game))

    with Session(db_engine) as observer:
        moves = select(GameMove).where(GameMove.game_id == real_game)
        assert [m.kind for m in observer.scalars(moves)] == [kind]
