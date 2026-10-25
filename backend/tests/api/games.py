"""Shared pieces for the game API tests: a puzzle, a fixed clock, two users.

The fixtures that use these live in ``tests/api/conftest.py``.
"""

from datetime import date, datetime

from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app import clock
from app.database.models.puzzles import Puzzle, PuzzleSolution
from app.database.models.users import User
from sudoku.solver import unique_solution

TODAY = "/api/puzzles/today"
GAMES = "/api/games"

GIVENS = "000090001084000000092040000007203000600514002000000300000000960000000700001078400"
_solution = unique_solution(GIVENS)
assert _solution is not None
SOLUTION: str = _solution

# 21:30 UTC on 24 October is 23:30 in Berlin: still the 24th there.
NOW = datetime(2026, 10, 24, 21, 30, tzinfo=clock.UTC)
DAY = date(2026, 10, 24)


def make_puzzle(db: Session, day: date, difficulty: str) -> Puzzle:
    puzzle = Puzzle(
        puzzle_date=day,
        difficulty=difficulty,
        givens=GIVENS,
        clue_count=26,
        hardest_technique="naked_triple",
        technique_counts={},
        generator_version="1",
        seed=1,
    )
    db.add(puzzle)
    db.flush()
    db.add(PuzzleSolution(puzzle_id=puzzle.id, solution=SOLUTION))
    db.commit()
    return puzzle


def other_user(db: Session, intra_id: int = 777, login: str = "bob") -> User:
    other = User(intra_id=intra_id, login=login, campus_id=1, campus_name="Berlin")
    db.add(other)
    db.commit()
    return other


def start(client: TestClient, difficulty: str = "hard") -> Response:
    return client.post(GAMES, json={"difficulty": difficulty})
