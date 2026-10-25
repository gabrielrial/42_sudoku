"""``GET /api/puzzles/today`` and ``POST /api/games`` (``API.md``; ``GAME_RULES.md`` §2).

The clock is fixed per test (``app.clock.now``), so "today" is whatever the test
says, and puzzles are written straight into the database.
"""

from collections.abc import Callable
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.database.models.game_sessions import GameSession
from app.database.models.users import User
from app.services import games as games_service
from tests.api.games import DAY, GAMES, GIVENS, NOW, SOLUTION, TODAY
from tests.api.games import make_puzzle as _puzzle
from tests.api.games import other_user as _other_user
from tests.api.games import start as _start
from tests.api.helpers import error_code, sign_in

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fixed_clock")]


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
        "continuing": [],
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


# --- continuing: yesterday's game, still open after midnight (GAME_RULES.md §3) ----------

BERLIN_MIDNIGHT = datetime(2026, 10, 24, 22, 0, tzinfo=clock.UTC)  # 00:00 on the 25th


def _yesterdays_game(db: Session, client: TestClient, last_contact: datetime) -> str:
    """Today's (the 24th's) Hard, started at 23:30 and last touched at ``last_contact``."""
    game_id = _start(client, "hard").json()["game_id"]
    game = db.get(GameSession, game_id)
    assert game is not None
    game.last_activity_at = last_contact
    db.commit()
    assert isinstance(game_id, str)
    return game_id


def test_back_after_midnight_the_open_game_is_listed(
    db: Session, signed_in: TestClient, week: dict, fixed_clock: Callable[[datetime], None]
) -> None:
    # The tab closed at 23:58; the home page reopened at 00:05: seven idle minutes.
    game_id = _yesterdays_game(db, signed_in, BERLIN_MIDNIGHT - timedelta(minutes=2))
    fixed_clock(BERLIN_MIDNIGHT + timedelta(minutes=5))

    body = signed_in.get(TODAY).json()

    assert body["date"] == "2026-10-25"
    assert body["continuing"] == [{"game_id": game_id, "difficulty": "hard", "date": "2026-10-24"}]
    assert [p["status"] for p in body["puzzles"]] == ["not_started"] * 3  # the 25th's own


def test_before_midnight_nothing_is_continuing(signed_in: TestClient, week: dict) -> None:
    _start(signed_in, "hard")

    assert signed_in.get(TODAY).json()["continuing"] == []


@pytest.mark.parametrize(
    ("last_contact", "now"),
    [
        # Idle for 16 minutes: closed.
        (BERLIN_MIDNIGHT - timedelta(minutes=2), BERLIN_MIDNIGHT + timedelta(minutes=14)),
        # Played until a second before 02:00: closed at 02:00 regardless.
        (
            BERLIN_MIDNIGHT + timedelta(hours=1, minutes=59, seconds=59),
            BERLIN_MIDNIGHT + timedelta(hours=2),
        ),
    ],
    ids=["idle", "past 02:00"],
)
def test_a_closed_game_is_not_continuing(
    db: Session,
    signed_in: TestClient,
    week: dict,
    fixed_clock: Callable[[datetime], None],
    last_contact: datetime,
    now: datetime,
) -> None:
    _yesterdays_game(db, signed_in, last_contact)
    fixed_clock(now)

    assert signed_in.get(TODAY).json()["continuing"] == []


def test_a_completed_game_is_not_continuing(
    db: Session, signed_in: TestClient, week: dict, fixed_clock: Callable[[datetime], None]
) -> None:
    game_id = _yesterdays_game(db, signed_in, BERLIN_MIDNIGHT - timedelta(minutes=2))
    game = db.get(GameSession, game_id)
    assert game is not None
    game.completed_at = BERLIN_MIDNIGHT - timedelta(minutes=2)
    db.commit()
    fixed_clock(BERLIN_MIDNIGHT + timedelta(minutes=5))

    assert signed_in.get(TODAY).json()["continuing"] == []


def test_someone_elses_open_game_is_not_continuing(
    db: Session,
    db_client: TestClient,
    user: User,
    week: dict,
    fixed_clock: Callable[[datetime], None],
) -> None:
    sign_in(db_client, db, _other_user(db))
    _yesterdays_game(db, db_client, BERLIN_MIDNIGHT - timedelta(minutes=2))
    fixed_clock(BERLIN_MIDNIGHT + timedelta(minutes=5))

    sign_in(db_client, db, user)
    assert db_client.get(TODAY).json()["continuing"] == []


def test_yesterdays_game_and_todays_can_be_held_at_once(
    db: Session, signed_in: TestClient, week: dict, fixed_clock: Callable[[datetime], None]
) -> None:
    # GAME_RULES.md §3: a continuing past-day session and today's puzzle are
    # different puzzles and do not conflict.
    yesterdays = _yesterdays_game(db, signed_in, BERLIN_MIDNIGHT - timedelta(minutes=2))
    fixed_clock(BERLIN_MIDNIGHT + timedelta(minutes=5))

    todays = _start(signed_in, "hard")

    assert todays.status_code == 201
    assert todays.json()["date"] == "2026-10-25"
    body = signed_in.get(TODAY).json()
    assert body["continuing"][0]["game_id"] == yesterdays
    assert body["puzzles"][2] | {"game_id": None} == {
        "difficulty": "hard",
        "status": "in_progress",
        "game_id": None,
        "official_seconds": None,
        "active_seconds": None,
    }
    assert body["puzzles"][2]["game_id"] == todays.json()["game_id"] != yesterdays
    assert GIVENS not in signed_in.get(TODAY).text  # still never a cell


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
