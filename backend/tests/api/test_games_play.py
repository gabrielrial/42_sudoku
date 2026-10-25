"""``PUT /api/games/{id}/cells/{index}`` and ``POST /api/games/{id}/heartbeat``.

``GAME_RULES.md`` §3 and ``SECURITY.md``: an input is checked for legality,
never for correctness; activity is measured by the server's clock alone; every
input is rate-limited per game; and none of it ever reads the solution.
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

from app import clock
from app.database.models.game_sessions import GameSession
from app.database.models.users import User
from app.services.rate_limit import RateLimiter
from tests.api.games import GAMES, GIVENS, NOW, SOLUTION, other_user, start
from tests.api.helpers import error_code, sign_in

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fixed_clock", "week")]

EMPTY = GIVENS.index("0")
"""The first cell the player may fill."""
GIVEN = next(i for i, ch in enumerate(GIVENS) if ch != "0")
"""The first cell that is part of the puzzle."""
RIGHT = int(SOLUTION[EMPTY])
WRONG = next(d for d in range(1, 10) if d != RIGHT)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def game_id(signed_in: TestClient) -> str:
    value = start(signed_in, "hard").json()["game_id"]
    assert isinstance(value, str)
    return value


def _put(client: TestClient, game_id: str, index: int, value: object) -> Response:
    return client.put(f"{GAMES}/{game_id}/cells/{index}", json={"value": value})


def _beat(client: TestClient, game_id: str) -> Response:
    return client.post(f"{GAMES}/{game_id}/heartbeat")


def _stored(db: Session, game_id: str) -> GameSession:
    db.expire_all()
    game = db.get(GameSession, uuid.UUID(game_id))
    assert game is not None
    return game


def _at(fixed_clock: Callable[[datetime], None], **delta: float) -> datetime:
    instant = NOW + timedelta(**delta)
    fixed_clock(instant)
    return instant


@pytest.fixture
def statements(db: Session) -> Iterator[list[str]]:
    """Every SQL statement the test's database connection runs, as text."""
    seen: list[str] = []

    def record(_conn: object, _cursor: object, statement: str, *_: object) -> None:
        seen.append(statement)

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", record)
    yield seen
    event.remove(connection, "before_cursor_execute", record)


# --- an input ------------------------------------------------------------------------------


def test_an_input_is_stored(db: Session, signed_in: TestClient, game_id: str) -> None:
    response = _put(signed_in, game_id, EMPTY, 4)

    assert response.status_code == 204
    assert response.content == b""
    assert _stored(db, game_id).state[EMPTY] == "4"


def test_null_clears_a_cell(db: Session, signed_in: TestClient, game_id: str) -> None:
    _put(signed_in, game_id, EMPTY, 4)

    assert _put(signed_in, game_id, EMPTY, None).status_code == 204
    assert _stored(db, game_id).state == GIVENS


def test_only_that_cell_changes(db: Session, signed_in: TestClient, game_id: str) -> None:
    _put(signed_in, game_id, EMPTY, 4)

    state = _stored(db, game_id).state
    assert state[:EMPTY] + state[EMPTY + 1 :] == GIVENS[:EMPTY] + GIVENS[EMPTY + 1 :]


def test_a_given_cannot_be_changed(db: Session, signed_in: TestClient, game_id: str) -> None:
    response = _put(signed_in, game_id, GIVEN, 1)

    assert response.status_code == 409
    assert error_code(response) == "cell_is_given"
    assert _stored(db, game_id).state == GIVENS


# --- legality, never correctness: the oracle --------------------------------------------------


def test_a_wrong_digit_is_an_ordinary_input(
    db: Session, signed_in: TestClient, game_id: str
) -> None:
    assert _put(signed_in, game_id, EMPTY, WRONG).status_code == 204
    assert _stored(db, game_id).state[EMPTY] == str(WRONG)


def test_a_right_and_a_wrong_digit_get_the_same_answer(signed_in: TestClient, game_id: str) -> None:
    # If these differed in anything, 729 requests would reveal the solution.
    right = _put(signed_in, game_id, EMPTY, RIGHT)
    wrong = _put(signed_in, game_id, EMPTY, WRONG)

    assert right.status_code == wrong.status_code == 204
    assert right.content == wrong.content == b""

    def headers(r: Response) -> dict[str, str]:
        return {k: v for k, v in r.headers.items() if k != "date"}

    assert headers(right) == headers(wrong)  # names and values


def test_playing_never_reads_the_solution(
    signed_in: TestClient, game_id: str, statements: list[str]
) -> None:
    _put(signed_in, game_id, EMPTY, RIGHT)
    _beat(signed_in, game_id)

    assert statements, "the listener saw nothing: the test would pass vacuously"
    assert not [s for s in statements if "puzzle_solutions" in s]


WRITES: dict[str, Callable[[TestClient, str], Response]] = {
    "input": lambda c, g: _put(c, g, EMPTY, 4),
    "heartbeat": _beat,
    "complete": lambda c, g: c.post(f"{GAMES}/{g}/complete"),
}


@pytest.mark.parametrize("send", WRITES.values(), ids=WRITES.keys())
def test_every_write_locks_its_game_row(
    db: Session,
    signed_in: TestClient,
    game_id: str,
    statements: list[str],
    send: Callable[[TestClient, str], Response],
) -> None:
    # Two requests on one game take turns. Without the lock, two correct
    # submissions at once would both count, and the second would move
    # completed_at; two inputs could overwrite each other's cell.
    game = _stored(db, game_id)
    game.state = SOLUTION  # so that complete gets as far as checking
    db.commit()
    statements.clear()

    assert send(signed_in, game_id).status_code in (200, 204)

    assert [s for s in statements if "FOR UPDATE OF game_sessions" in s]


# --- what a request may say --------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, 10, -1, "7", 7.0, True, [7], {"v": 7}])
def test_a_value_that_is_not_1_to_9_or_null_is_422(
    db: Session, signed_in: TestClient, game_id: str, value: object
) -> None:
    response = _put(signed_in, game_id, EMPTY, value)

    assert response.status_code == 422
    assert error_code(response) == "invalid_request"
    assert _stored(db, game_id).state == GIVENS


def test_a_missing_value_is_422_not_a_clear(signed_in: TestClient, game_id: str) -> None:
    response = signed_in.put(f"{GAMES}/{game_id}/cells/{EMPTY}", json={})

    assert response.status_code == 422


@pytest.mark.parametrize("index", ["-1", "81", "1000", "x", "4.5"])
def test_an_index_outside_0_to_80_is_422(signed_in: TestClient, game_id: str, index: str) -> None:
    response = signed_in.put(f"{GAMES}/{game_id}/cells/{index}", json={"value": 1})

    assert response.status_code == 422


# --- whose game, and is it still open --------------------------------------------------------


def test_someone_elses_game_is_404_and_untouched(
    db: Session, db_client: TestClient, user: User
) -> None:
    sign_in(db_client, db, user)
    game_id = start(db_client).json()["game_id"]
    sign_in(db_client, db, other_user(db))

    put = _put(db_client, game_id, EMPTY, 4)
    beat = _beat(db_client, game_id)

    assert put.status_code == beat.status_code == 404
    assert _stored(db, game_id).state == GIVENS


@pytest.mark.parametrize("send", [lambda c, g: _put(c, g, EMPTY, 4), _beat], ids=["input", "beat"])
def test_a_completed_game_takes_nothing(
    db: Session, signed_in: TestClient, game_id: str, send: Callable[[TestClient, str], Response]
) -> None:
    game = _stored(db, game_id)
    game.completed_at = NOW
    db.commit()

    response = send(signed_in, game_id)

    assert response.status_code == 409
    assert error_code(response) == "game_completed"


@pytest.mark.parametrize("send", [lambda c, g: _put(c, g, EMPTY, 4), _beat], ids=["input", "beat"])
def test_a_closed_game_takes_nothing(
    signed_in: TestClient,
    game_id: str,
    fixed_clock: Callable[[datetime], None],
    send: Callable[[TestClient, str], Response],
) -> None:
    _at(fixed_clock, hours=12)  # 09:30 on the 25th, left since 21:30 UTC

    response = send(signed_in, game_id)

    assert response.status_code == 410
    assert error_code(response) == "game_closed"


def test_inputs_keep_a_game_alive_past_midnight(
    signed_in: TestClient, game_id: str, fixed_clock: Callable[[datetime], None]
) -> None:
    # Started 23:30 on the 24th. An input every ten minutes carries it past
    # midnight; it is still the 24th's game.
    for minutes in (10, 20, 30, 40):
        _at(fixed_clock, minutes=minutes)
        assert _put(signed_in, game_id, EMPTY, 4).status_code == 204

    _at(fixed_clock, minutes=54)  # 14 minutes after the last input, at 00:24
    assert signed_in.get(f"{GAMES}/{game_id}").json()["status"] == "in_progress"
    _at(fixed_clock, minutes=56)  # 16 minutes: closed
    assert signed_in.get(f"{GAMES}/{game_id}").status_code == 410


def test_heartbeats_cannot_carry_a_game_past_two_oclock(
    signed_in: TestClient, game_id: str, fixed_clock: Callable[[datetime], None]
) -> None:
    # 23:30 + 2h29m59s is 01:59:59 Berlin; heartbeats every minute until then,
    # every one of them accepted (a limiter on the real clock would refuse most,
    # and the game would close by idleness instead: the wrong reason).
    _fake_limiter(signed_in, "heartbeat_limiter", 1000, 1)
    for minutes in range(1, 150):
        _at(fixed_clock, minutes=minutes, seconds=59)
        assert _beat(signed_in, game_id).status_code == 204
    _at(fixed_clock, hours=2, minutes=30)  # 02:00:00, a second after the last one

    assert _beat(signed_in, game_id).status_code == 410


# --- active time: the server's arithmetic ------------------------------------------------------


def test_contacts_close_together_are_active_time(
    db: Session, signed_in: TestClient, game_id: str, fixed_clock: Callable[[datetime], None]
) -> None:
    _at(fixed_clock, seconds=30)
    _put(signed_in, game_id, EMPTY, 4)
    _at(fixed_clock, seconds=90)
    _beat(signed_in, game_id)

    game = _stored(db, game_id)
    assert game.active_seconds == 90
    assert game.last_activity_at == NOW + timedelta(seconds=90)


def test_a_long_gap_is_absence_not_play(
    db: Session, signed_in: TestClient, game_id: str, fixed_clock: Callable[[datetime], None]
) -> None:
    _at(fixed_clock, seconds=90)  # exactly the limit: counted
    _put(signed_in, game_id, EMPTY, 4)
    _at(fixed_clock, seconds=90 + 91)  # one second over: not counted
    _put(signed_in, game_id, EMPTY, 5)

    assert _stored(db, game_id).active_seconds == 90


def test_active_time_cannot_be_stated_by_the_client(
    db: Session, signed_in: TestClient, game_id: str, fixed_clock: Callable[[datetime], None]
) -> None:
    # Whatever a request carries, only the server's clock moves the figure.
    _at(fixed_clock, seconds=10)
    signed_in.post(f"{GAMES}/{game_id}/heartbeat", json={"active_seconds": 99999})

    assert _stored(db, game_id).active_seconds == 10


# --- rate limits, per game -----------------------------------------------------------------------


def _fake_limiter(client: TestClient, name: str, capacity: int, per_second: float) -> FakeClock:
    app = client.app
    assert isinstance(app, FastAPI)
    fake = FakeClock()
    setattr(
        app.state, name, RateLimiter(capacity=capacity, refill_per_second=per_second, clock=fake)
    )
    return fake


def test_ten_quick_inputs_pass_and_the_eleventh_waits(
    db: Session, signed_in: TestClient, game_id: str
) -> None:
    limiter_clock = _fake_limiter(signed_in, "input_limiter", 10, 1)
    for value in [1, 2, 3, 4, 5, 6, 7, 8, 9, 1]:
        assert _put(signed_in, game_id, EMPTY, value).status_code == 204

    response = _put(signed_in, game_id, EMPTY, 2)

    assert response.status_code == 429
    assert error_code(response) == "too_many_requests"
    assert response.headers["retry-after"] == "1"
    assert _stored(db, game_id).state[EMPTY] == "1"  # the refused one changed nothing
    limiter_clock.now += 1
    assert _put(signed_in, game_id, EMPTY, 2).status_code == 204


def test_the_input_limit_is_per_game(signed_in: TestClient, game_id: str) -> None:
    _fake_limiter(signed_in, "input_limiter", 10, 1)
    for _ in range(10):
        _put(signed_in, game_id, EMPTY, 4)
    other_game = start(signed_in, "easy").json()["game_id"]

    assert _put(signed_in, other_game, EMPTY, 4).status_code == 204


def test_nobody_else_can_spend_my_inputs(db: Session, db_client: TestClient, user: User) -> None:
    # The limit is taken after ownership: requests on a game that is not yours
    # stop at 404 and cost its owner nothing.
    sign_in(db_client, db, user)
    _fake_limiter(db_client, "input_limiter", 10, 1)
    game_id = start(db_client).json()["game_id"]
    sign_in(db_client, db, other_user(db))
    for _ in range(30):
        assert _put(db_client, game_id, EMPTY, 4).status_code == 404

    sign_in(db_client, db, user)
    assert _put(db_client, game_id, EMPTY, 4).status_code == 204


def test_two_heartbeats_a_minute(signed_in: TestClient, game_id: str) -> None:
    _fake_limiter(signed_in, "heartbeat_limiter", 2, 2 / 60)

    assert _beat(signed_in, game_id).status_code == 204
    assert _beat(signed_in, game_id).status_code == 204
    response = _beat(signed_in, game_id)

    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"


@pytest.mark.parametrize(
    ("limiter", "capacity", "per_minute"),
    [
        ("input_limiter", 10, 60),  # D22: a burst of 10, one a second
        ("heartbeat_limiter", 2, 2),  # D5
        ("completion_limiter", 5, 5),  # D5: the brute-force path
        ("login_limiter", 5, 5),  # D5
    ],
)
def test_every_limit_has_its_decided_default(
    signed_in: TestClient, limiter: str, capacity: int, per_minute: int
) -> None:
    app = signed_in.app
    assert isinstance(app, FastAPI)
    bucket = getattr(app.state, limiter)

    assert bucket.capacity == capacity
    assert bucket.refill_per_second * 60 == pytest.approx(per_minute)


# --- the instant a request is judged at: after the lock, not before (review M4) ----------


def test_writes_read_the_clock_after_taking_the_lock(
    db: Session, signed_in: TestClient, game_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A request that waits behind another on the row lock must be judged at the
    # time it proceeds. Recorded as one timeline: SQL statements and clock reads.
    timeline: list[str] = []

    def record(_conn: object, _cursor: object, statement: str, *_: object) -> None:
        timeline.append("lock" if "FOR UPDATE" in statement else "sql")

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", record)
    monkeypatch.setattr(clock, "now", lambda: timeline.append("clock") or NOW)
    game = _stored(db, game_id)
    game.state = SOLUTION
    db.commit()
    requests = {
        "input": lambda: _put(signed_in, game_id, EMPTY, RIGHT),
        "heartbeat": lambda: _beat(signed_in, game_id),
        "complete": lambda: signed_in.post(f"{GAMES}/{game_id}/complete"),
    }
    try:
        for name, send in requests.items():
            timeline.clear()
            assert send().status_code in (200, 204), name
            # One reading, after the lock: every write of the request uses it.
            assert timeline.count("clock") == 1, f"{name}: {timeline}"
            assert "lock" in timeline, name
            assert timeline.index("clock") > timeline.index("lock"), f"{name}: {timeline}"
    finally:
        event.remove(connection, "before_cursor_execute", record)


def test_the_input_refill_rate_is_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import main
    from app.config import get_settings

    settings = get_settings().model_copy(update={"game_inputs_per_second": 2.0})
    monkeypatch.setattr(main, "get_settings", lambda: settings)

    assert main.create_app().state.input_limiter.refill_per_second == 2.0


# --- the clock going backwards (review S4) ---------------------------------------------------


def test_a_contact_older_than_the_last_one_changes_no_time(
    db: Session, signed_in: TestClient, game_id: str, fixed_clock: Callable[[datetime], None]
) -> None:
    # Happens for real: a request reads the clock, then the one ahead of it on
    # the lock writes a later last_activity_at. Neither negative active time nor
    # last_activity_at moving back may follow.
    later = NOW + timedelta(seconds=10)
    game = _stored(db, game_id)
    game.last_activity_at = later
    db.commit()
    _at(fixed_clock, seconds=5)

    assert _put(signed_in, game_id, EMPTY, 4).status_code == 204

    game = _stored(db, game_id)
    assert game.active_seconds == 0
    assert game.last_activity_at == later


# --- signed in, and a well-formed id, on every write (review M7) ----------------------------


@pytest.mark.parametrize("send", WRITES.values(), ids=WRITES.keys())
def test_every_write_needs_a_session(
    db_client: TestClient, send: Callable[[TestClient, str], Response]
) -> None:
    response = send(db_client, str(uuid.uuid4()))

    assert response.status_code == 401
    assert error_code(response) == "not_authenticated"


@pytest.mark.parametrize("bad_id", ["not-a-uuid", "1", "' OR 1=1 --"])
@pytest.mark.parametrize("send", WRITES.values(), ids=WRITES.keys())
def test_every_write_answers_404_for_a_malformed_id(
    signed_in: TestClient, send: Callable[[TestClient, str], Response], bad_id: str
) -> None:
    response = send(signed_in, bad_id)

    assert response.status_code == 404
    assert error_code(response) == "game_not_found"
