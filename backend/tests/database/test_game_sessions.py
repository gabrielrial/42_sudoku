"""``game_sessions``: the rules the database itself enforces (``DATA_MODEL.md``).

One game per user per puzzle, forever (D3); a game bound to its puzzle, which
cannot be deleted under it (D6/D7); a well-formed grid; and a user's games
gone with the user.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.database.models.game_sessions import GameSession
from app.database.models.puzzles import Puzzle
from app.database.models.users import User

pytestmark = pytest.mark.db

GIVENS = "000090001084000000092040000007203000600514002000000300000000960000000700001078400"


@pytest.fixture
def puzzle(db: Session) -> Puzzle:
    row = Puzzle(
        puzzle_date=date(2026, 10, 24),
        difficulty="hard",
        givens=GIVENS,
        clue_count=26,
        hardest_technique="naked_triple",
        technique_counts={},
        generator_version="1",
        seed=5,
    )
    db.add(row)
    db.commit()
    return row


def _game(user: User, puzzle: Puzzle, **changes: object) -> GameSession:
    values: dict[str, object] = {"user_id": user.id, "puzzle_id": puzzle.id, "state": GIVENS}
    values.update(changes)
    return GameSession(**values)


def _refused(db: Session, row: object, error: type[Exception] = IntegrityError) -> None:
    with pytest.raises(error):
        db.add(row)
        db.flush()
    db.rollback()


def test_a_new_game_starts_from_the_database_defaults(
    db: Session, user: User, puzzle: Puzzle
) -> None:
    game = _game(user, puzzle)
    db.add(game)
    db.flush()

    # Read back on insert (eager_defaults), not left as None on the object.
    assert isinstance(game.id, uuid.UUID)
    assert (game.state_version, game.active_seconds, game.submission_count) == (1, 0, 0)
    assert game.started_at is not None and game.last_activity_at is not None
    assert game.completed_at is None and game.closed_at is None


def test_a_second_game_of_the_same_puzzle_is_refused(
    db: Session, user: User, puzzle: Puzzle
) -> None:
    # D3: starting is irreversible; there is no second attempt.
    db.add(_game(user, puzzle))
    db.flush()

    _refused(db, _game(user, puzzle))


def test_two_users_play_the_same_puzzle(db: Session, user: User, puzzle: Puzzle) -> None:
    other = User(intra_id=999, login="bob", campus_id=1, campus_name="Berlin")
    db.add(other)
    db.flush()

    db.add_all([_game(user, puzzle), _game(other, puzzle)])
    db.flush()

    assert db.scalar(select(func.count()).select_from(GameSession)) == 2


@pytest.mark.parametrize(
    "state", [GIVENS[:80], "x" + GIVENS[1:], "." + GIVENS[1:]], ids=["80", "letter", "dot"]
)
def test_a_malformed_state_is_refused(db: Session, user: User, puzzle: Puzzle, state: str) -> None:
    _refused(db, _game(user, puzzle, state=state), error=DBAPIError)


def test_a_puzzle_with_games_cannot_be_deleted(db: Session, user: User, puzzle: Puzzle) -> None:
    # D6/D7: the binding is immutable; ON DELETE RESTRICT keeps it so.
    db.add(_game(user, puzzle))
    db.flush()

    with pytest.raises(IntegrityError):
        db.delete(puzzle)
        db.flush()
    db.rollback()


def test_deleting_a_user_deletes_their_games(db: Session, user: User, puzzle: Puzzle) -> None:
    db.add(_game(user, puzzle))
    db.flush()

    db.delete(user)
    db.flush()

    assert db.scalar(select(func.count()).select_from(GameSession)) == 0
