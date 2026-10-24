"""``GET /api/puzzles/today`` and ``POST /api/games`` (``API.md``; ``GAME_RULES.md`` §2).

The clock is fixed per test (``app.clock.now``), so "today" is whatever the test
says, and puzzles are written straight into the database.
"""

from collections.abc import Callable
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.database.models.game_sessions import GameSession
from app.database.models.puzzles import Puzzle, PuzzleSolution
from app.database.models.users import User
from app.services import games as games_service
from sudoku.solver import unique_solution
from tests.api.helpers import error_code, sign_in

pytestmark = pytest.mark.db

TODAY = "/api/puzzles/today"
GAMES = "/api/games"

GIVENS = "000090001084000000092040000007203000600514002000000300000000960000000700001078400"
SOLUTION = unique_solution(GIVENS)
assert SOLUTION is not None
# 21:30 UTC on 24 October is 23:30 in Berlin: still the 24th there.
NOW = datetime(2026, 10, 24, 21, 30, tzinfo=clock.UTC)
DAY = date(2026, 10, 24)


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> Callable[[datetime], None]:
    def set_now(instant: datetime) -> None:
        monkeypatch.setattr(clock, "now", lambda: instant)

    set_now(NOW)
    return set_now


def _puzzle(db: Session, day: date, difficulty: str) -> Puzzle:
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


@pytest.fixture
def week(db: Session) -> dict[tuple[date, str], Puzzle]:
    """Yesterday's, today's and tomorrow's puzzles, all three difficulties."""
    return {
        (day, d): _puzzle(db, day, d)
        for day in (DAY - timedelta(days=1), DAY, DAY + timedelta(days=1))
        for d in ("easy", "medium", "hard")
    }


@pytest.fixture
def signed_in(db: Session, db_client: TestClient, user: User) -> TestClient:
    sign_in(db_client, db, user)
    return db_client


def _start(client: TestClient, difficulty: str = "hard") -> Response:
    return client.post(GAMES, json={"difficulty": difficulty})


def _other_user(db: Session) -> User:
    other = User(intra_id=777, login="bob", campus_id=1, campus_name="Berlin")
    db.add(other)
    db.commit()
    return other


# --- signed in only -----------------------------------------------------------------------


@pytest.mark.parametrize(("method", "path"), [("GET", TODAY), ("POST", GAMES)])
def test_both_need_a_session(db_client: TestClient, method: str, path: str) -> None:
    response = db_client.request(method, path, json={"difficulty": "easy"})

    assert response.status_code == 401
    assert error_code(response) == "not_authenticated"


# --- GET /api/puzzles/today -----------------------------------------------------------------


def test_today_lists_the_three_difficulties_not_started(signed_in: TestClient, week: dict) -> None:
    body = signed_in.get(TODAY).json()

    assert body == {
        "date": "2026-10-24",
        "puzzles": [
            {
                "difficulty": d,
                "status": "not_started",
                "game_id": None,
                "official_seconds": None,
                "active_seconds": None,
            }
            for d in ("easy", "medium", "hard")
        ],
    }


def test_today_never_shows_a_cell(signed_in: TestClient, week: dict) -> None:
    # Q13: seeing the puzzle is starting the clock. Not the givens, not the
    # solution, not anything 81 characters long.
    _start(signed_in, "easy")  # even with a game started

    text = signed_in.get(TODAY).text

    assert GIVENS not in text
    assert SOLUTION not in text
    assert "givens" not in text and "state" not in text


def test_today_is_the_berlin_day(
    signed_in: TestClient, week: dict, fixed_clock: Callable[[datetime], None]
) -> None:
    fixed_clock(datetime(2026, 10, 24, 22, 30, tzinfo=clock.UTC))  # 00:30 on the 25th in Berlin

    assert signed_in.get(TODAY).json()["date"] == "2026-10-25"


def test_a_started_game_shows_in_progress_with_its_id(signed_in: TestClient, week: dict) -> None:
    game_id = _start(signed_in, "medium").json()["game_id"]

    puzzles = {p["difficulty"]: p for p in signed_in.get(TODAY).json()["puzzles"]}

    assert puzzles["medium"]["status"] == "in_progress"
    assert puzzles["medium"]["game_id"] == game_id
    assert puzzles["easy"]["status"] == puzzles["hard"]["status"] == "not_started"


def test_a_completed_game_shows_its_times(db: Session, signed_in: TestClient, week: dict) -> None:
    game_id = _start(signed_in, "easy").json()["game_id"]
    game = db.get(GameSession, game_id)
    assert game is not None
    game.completed_at = game.started_at + timedelta(minutes=6, seconds=52)
    game.active_seconds = 388
    db.commit()

    easy = signed_in.get(TODAY).json()["puzzles"][0]

    assert easy == {
        "difficulty": "easy",
        "status": "completed",
        "game_id": game_id,
        "official_seconds": 412,
        "active_seconds": 388,
    }


def test_another_users_game_does_not_show(
    db: Session, db_client: TestClient, user: User, week: dict
) -> None:
    sign_in(db_client, db, _other_user(db))
    _start(db_client, "hard")

    sign_in(db_client, db, user)
    statuses = [p["status"] for p in db_client.get(TODAY).json()["puzzles"]]

    assert statuses == ["not_started"] * 3


def test_a_difficulty_without_a_puzzle_today_is_left_out(
    db: Session, signed_in: TestClient
) -> None:
    _puzzle(db, DAY, "easy")

    assert [p["difficulty"] for p in signed_in.get(TODAY).json()["puzzles"]] == ["easy"]


# --- POST /api/games ---------------------------------------------------------------------------


def test_starting_returns_todays_grid_and_starts_the_clock(
    signed_in: TestClient, week: dict
) -> None:
    response = _start(signed_in, "hard")

    assert response.status_code == 201
    body = response.json()
    assert body["difficulty"] == "hard"
    assert body["date"] == "2026-10-24"
    assert body["givens"] == body["state"] == GIVENS
    assert datetime.fromisoformat(body["started_at"]) == NOW
    assert set(body) == {"game_id", "difficulty", "date", "givens", "state", "started_at"}


def test_the_game_is_bound_to_todays_puzzle(db: Session, signed_in: TestClient, week: dict) -> None:
    game = db.get(GameSession, _start(signed_in, "hard").json()["game_id"])

    assert game is not None
    assert game.puzzle_id == week[(DAY, "hard")].id  # not yesterday's, not tomorrow's


def test_after_berlin_midnight_it_is_the_new_days_puzzle(
    db: Session, signed_in: TestClient, week: dict, fixed_clock: Callable[[datetime], None]
) -> None:
    fixed_clock(datetime(2026, 10, 24, 22, 0, 1, tzinfo=clock.UTC))  # 00:00:01 on the 25th

    game = db.get(GameSession, _start(signed_in, "hard").json()["game_id"])

    assert game is not None
    assert game.puzzle_id == week[(DAY + timedelta(days=1), "hard")].id


def test_starting_never_reveals_the_solution(signed_in: TestClient, week: dict) -> None:
    assert SOLUTION not in _start(signed_in, "hard").text


def test_a_second_start_is_409_with_the_existing_game(signed_in: TestClient, week: dict) -> None:
    first = _start(signed_in, "hard").json()["game_id"]

    response = _start(signed_in, "hard")

    assert response.status_code == 409
    assert error_code(response) == "game_already_exists"
    assert response.json()["error"]["game_id"] == first  # so the client can resume


def test_a_second_start_creates_nothing(db: Session, signed_in: TestClient, week: dict) -> None:
    _start(signed_in, "hard")
    _start(signed_in, "hard")

    assert db.scalar(select(func.count()).select_from(GameSession)) == 1


def test_two_starts_racing_end_in_one_game_and_a_409(
    db: Session, signed_in: TestClient, week: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Two requests at once both see no game yet; the unique constraint lets one
    # through. Simulated by a second request that cannot see the first game.
    first = _start(signed_in, "hard").json()["game_id"]
    monkeypatch.setattr(games_service, "_game_of", _blind_once(games_service._game_of))

    response = _start(signed_in, "hard")

    assert response.status_code == 409
    assert response.json()["error"]["game_id"] == first
    assert db.scalar(select(func.count()).select_from(GameSession)) == 1


def _blind_once(real: Callable[..., GameSession | None]) -> Callable[..., GameSession | None]:
    """``_game_of`` that misses the game the first time it is asked."""
    asked = []

    def game_of(*args: object) -> GameSession | None:
        asked.append(args)
        return None if len(asked) == 1 else real(*args)

    return game_of


def test_each_difficulty_is_its_own_game(signed_in: TestClient, week: dict) -> None:
    ids = {_start(signed_in, d).json()["game_id"] for d in ("easy", "medium", "hard")}

    assert len(ids) == 3


def test_another_user_starts_the_same_puzzle(
    db: Session, db_client: TestClient, user: User, week: dict
) -> None:
    sign_in(db_client, db, user)
    assert _start(db_client).status_code == 201

    sign_in(db_client, db, _other_user(db))
    assert _start(db_client).status_code == 201


def test_no_puzzle_today_is_503(db: Session, signed_in: TestClient) -> None:
    _puzzle(db, DAY - timedelta(days=1), "hard")  # only yesterday's exists

    response = _start(signed_in, "hard")

    assert response.status_code == 503
    assert error_code(response) == "puzzle_unavailable"


@pytest.mark.parametrize(
    "body", [{"difficulty": "expert"}, {"difficulty": "Hard"}, {}, {"date": "2026-10-23"}]
)
def test_a_bad_body_is_422(signed_in: TestClient, week: dict, body: dict) -> None:
    response = signed_in.post(GAMES, json=body)

    assert response.status_code == 422
    assert error_code(response) == "invalid_request"


def test_a_date_in_the_body_cannot_pick_another_day(
    db: Session, signed_in: TestClient, week: dict
) -> None:
    # D6 as an API shape: the endpoint takes a difficulty, never a date.
    response = signed_in.post(GAMES, json={"difficulty": "hard", "date": "2026-10-23"})

    game = db.get(GameSession, response.json()["game_id"])
    assert game is not None
    assert game.puzzle_id == week[(DAY, "hard")].id
