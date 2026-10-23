"""``puzzles`` and ``puzzle_solutions``: the rules the database itself enforces.

``DATA_MODEL.md``, "Constraints that carry product rules": one puzzle per day
per difficulty, well-formed grids, and a solution that goes with its puzzle.
These tests check that PostgreSQL refuses what the application must never
write, whatever the application does.
"""

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.database.models.puzzles import Puzzle, PuzzleSolution
from sudoku.solver import unique_solution

pytestmark = pytest.mark.db

GIVENS = "000090001084000000092040000007203000600514002000000300000000960000000700001078400"
SOLUTION = unique_solution(GIVENS)
DAY = date(2026, 10, 25)  # the long Berlin day: storage does not care, only "today" does


def _puzzle(**changes: object) -> Puzzle:
    values: dict[str, object] = {
        "puzzle_date": DAY,
        "difficulty": "hard",
        "givens": GIVENS,
        "clue_count": 26,
        "hardest_technique": "naked_triple",
        "technique_counts": {"naked_triple": 1},
        "generator_version": "1",
        "seed": 5,
    }
    values.update(changes)
    return Puzzle(**values)


def _save(db: Session, *rows: object) -> None:
    db.add_all(rows)
    db.flush()


def _refused(db: Session, *rows: object, error: type[Exception] = IntegrityError) -> None:
    with pytest.raises(error):
        _save(db, *rows)
    db.rollback()


# --- a well-formed puzzle --------------------------------------------------------------


def test_a_puzzle_and_its_solution_are_saved(db: Session) -> None:
    puzzle = _puzzle()
    _save(db, puzzle)
    _save(db, PuzzleSolution(puzzle_id=puzzle.id, solution=SOLUTION))

    db.expire_all()
    assert db.get(Puzzle, puzzle.id) is not None
    assert db.get(PuzzleSolution, puzzle.id).solution == SOLUTION  # type: ignore[union-attr]


def test_technique_counts_default_to_empty(db: Session) -> None:
    puzzle = _puzzle()
    del puzzle.technique_counts
    _save(db, puzzle)

    db.expire_all()
    assert db.get(Puzzle, puzzle.id).technique_counts == {}  # type: ignore[union-attr]


# --- one puzzle per day per difficulty (A1) ------------------------------------------------


def test_a_second_puzzle_for_the_same_day_and_difficulty_is_refused(db: Session) -> None:
    _save(db, _puzzle())

    _refused(db, _puzzle(seed=6))


def test_the_three_difficulties_of_one_day_coexist(db: Session) -> None:
    _save(db, *(_puzzle(difficulty=d) for d in ("easy", "medium", "hard")))

    assert db.scalar(select(func.count()).select_from(Puzzle)) == 3


def test_the_same_difficulty_on_another_day_is_another_puzzle(db: Session) -> None:
    _save(db, _puzzle(), _puzzle(puzzle_date=date(2026, 10, 26)))


# --- well-formed values only ---------------------------------------------------------------


@pytest.mark.parametrize("difficulty", ["expert", "Hard", ""])
def test_an_unknown_difficulty_is_refused(db: Session, difficulty: str) -> None:
    _refused(db, _puzzle(difficulty=difficulty))


BAD_GIVENS = {
    "80 characters": GIVENS[:80],  # CHAR(81) pads it with a space, which the check refuses
    "82 characters": GIVENS + "0",
    "a letter": "x" + GIVENS[1:],
    "a dot for an empty cell": "." + GIVENS[1:],
}


@pytest.mark.parametrize("givens", BAD_GIVENS.values(), ids=BAD_GIVENS.keys())
def test_malformed_givens_are_refused(db: Session, givens: str) -> None:
    _refused(db, _puzzle(givens=givens), error=DBAPIError)


BAD_SOLUTIONS = {
    "an empty cell": "0" + SOLUTION[1:],
    "80 characters": SOLUTION[:80],
    "a letter": "x" + SOLUTION[1:],
}


@pytest.mark.parametrize("solution", BAD_SOLUTIONS.values(), ids=BAD_SOLUTIONS.keys())
def test_malformed_solutions_are_refused(db: Session, solution: str) -> None:
    puzzle = _puzzle()
    _save(db, puzzle)

    _refused(db, PuzzleSolution(puzzle_id=puzzle.id, solution=solution), error=DBAPIError)


def test_a_solution_needs_its_puzzle(db: Session) -> None:
    _refused(db, PuzzleSolution(puzzle_id=999_999, solution=SOLUTION))


def test_a_puzzle_has_at_most_one_solution(db: Session) -> None:
    puzzle = _puzzle()
    _save(db, puzzle)
    _save(db, PuzzleSolution(puzzle_id=puzzle.id, solution=SOLUTION))
    db.expunge_all()  # a second object for the same key, as another request would make

    _refused(db, PuzzleSolution(puzzle_id=puzzle.id, solution=SOLUTION))


def test_deleting_a_puzzle_deletes_its_solution(db: Session) -> None:
    puzzle = _puzzle()
    _save(db, puzzle)
    _save(db, PuzzleSolution(puzzle_id=puzzle.id, solution=SOLUTION))

    db.delete(puzzle)
    db.flush()

    db.expire_all()
    assert db.get(PuzzleSolution, puzzle.id) is None


# --- the solution stays out of the ordinary read path ----------------------------------


def test_a_puzzle_cannot_bring_its_solution_along() -> None:
    # DATA_MODEL.md: leaking it must take a query that names PuzzleSolution,
    # not a relationship that a careless response model could follow.
    assert not Puzzle.__mapper__.relationships
    assert "solution" not in Puzzle.__table__.columns
