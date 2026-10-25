"""The solution never leaves the server (``AGENTS.md``, security floor; ``SECURITY.md``).

One walk through every game endpoint and every outcome a player can reach before
solving the puzzle — success, 404, 409, 410, 422, 429, and a game still open
past midnight — with four checks on every answer:

- it has the status the walk expects, so each part of the walk really ran;
- the solution does not appear in it;
- every JSON key in it is one the API defines. A field added carelessly — a
  ``solution``, a ``hint``, a count of right cells — fails here by its mere
  presence, whatever it would have carried;
- every grid in it is one the player already has: ``givens`` is the puzzle's,
  and ``state`` is a grid the server held for them at that point. An allowed
  field carrying more — a ``state`` with a solved cell filled in — fails here.

Once the player has solved the puzzle, their grid *is* the solution, and
showing it back to them leaks nothing; that state is deliberately not walked.
"""

from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.database.models.game_sessions import GameSession
from app.database.models.users import User
from app.services.rate_limit import RateLimiter
from tests.api.games import GAMES, GIVENS, NOW, SOLUTION, TODAY, other_user, start
from tests.api.helpers import sign_in

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fixed_clock", "week")]

API_KEYS = {
    # GET /api/puzzles/today
    "date", "puzzles", "continuing", "difficulty", "status", "game_id",
    "official_seconds", "active_seconds",
    # POST /api/games, GET /api/games/{id}
    "givens", "state", "started_at", "completed_at", "submission_count",
    # POST /api/games/{id}/complete
    "correct",
    # the error envelope
    "error", "code", "message",
}  # fmt: skip

EMPTY = GIVENS.index("0")
GIVEN = next(i for i, ch in enumerate(GIVENS) if ch != "0")


def _items(value: Any) -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key, inner
            yield from _items(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _items(inner)


def _keys(value: Any) -> Iterator[str]:
    return (key for key, _ in _items(value))


def test_no_answer_before_the_solve_leaks_anything(
    db: Session, db_client: TestClient, user: User, fixed_clock: Callable[[datetime], None]
) -> None:
    walk: list[tuple[str, Response, int]] = []

    def call(label: str, response: Response, expected: int) -> Response:
        walk.append((label, response, expected))
        return response

    app = db_client.app
    assert isinstance(app, FastAPI)
    # A frozen bucket: exactly ten inputs pass, the eleventh is refused.
    app.state.input_limiter = RateLimiter(capacity=10, refill_per_second=1, clock=lambda: 0.0)

    sign_in(db_client, db, user)
    call("today, nothing started", db_client.get(TODAY), 200)
    game_id = call("start", start(db_client, "hard"), 201).json()["game_id"]
    left_overnight = call("start another", start(db_client, "easy"), 201).json()["game_id"]
    game = f"{GAMES}/{game_id}"
    call("start again", start(db_client, "hard"), 409)
    call("start, unknown difficulty", db_client.post(GAMES, json={"difficulty": "x"}), 422)
    call("today, started", db_client.get(TODAY), 200)
    call("resume", db_client.get(game), 200)
    call(
        "resume, no such game", db_client.get(f"{GAMES}/00000000-0000-0000-0000-000000000000"), 404
    )
    for digit in range(1, 10):  # the right digit among them
        call(f"input {digit}", db_client.put(f"{game}/cells/{EMPTY}", json={"value": digit}), 204)
    call("input on a given", db_client.put(f"{game}/cells/{GIVEN}", json={"value": 1}), 409)
    call("input over the limit", db_client.put(f"{game}/cells/{EMPTY}", json={"value": 2}), 429)
    call("input, bad value", db_client.put(f"{game}/cells/{EMPTY}", json={"value": 0}), 422)
    call("heartbeat", db_client.post(f"{game}/heartbeat"), 204)
    call("complete, incomplete grid", db_client.post(f"{game}/complete"), 409)

    stored = db.get(GameSession, game_id)
    assert stored is not None
    wrong = list(SOLUTION)
    wrong[EMPTY] = "1" if wrong[EMPTY] != "1" else "2"
    stored.state = "".join(wrong)
    db.commit()
    call("complete, wrong grid", db_client.post(f"{game}/complete"), 200)
    call("resume after a wrong submission", db_client.get(game), 200)

    fixed_clock(NOW + timedelta(minutes=25))  # 23:55 in Berlin
    call("heartbeat before midnight", db_client.post(f"{game}/heartbeat"), 204)
    fixed_clock(NOW + timedelta(minutes=35))  # 00:05: the hard game goes on past midnight
    call("today, a game continuing", db_client.get(TODAY), 200)
    call("resume past midnight", db_client.get(game), 200)
    fixed_clock(NOW)

    sign_in(db_client, db, other_user(db))
    call("someone else: resume", db_client.get(game), 404)
    call("someone else: input", db_client.put(f"{game}/cells/{EMPTY}", json={"value": 1}), 404)
    call("someone else: heartbeat", db_client.post(f"{game}/heartbeat"), 404)
    call("someone else: complete", db_client.post(f"{game}/complete"), 404)
    call("someone else: today", db_client.get(TODAY), 200)

    sign_in(db_client, db, user)
    fixed_clock(NOW + timedelta(hours=12))  # the next morning: the easy game is closed
    closed = f"{GAMES}/{left_overnight}"
    call("closed: resume", db_client.get(closed), 410)
    call("closed: input", db_client.put(f"{closed}/cells/{EMPTY}", json={"value": 1}), 410)
    call("closed: heartbeat", db_client.post(f"{closed}/heartbeat"), 410)
    call("closed: complete", db_client.post(f"{closed}/complete"), 410)
    call("today, the next day", db_client.get(TODAY), 200)

    unexpected = [(label, r.status_code, want) for label, r, want in walk if r.status_code != want]
    assert not unexpected, f"the walk did not go where it claims: {unexpected}"
    leaks = [label for label, r, _ in walk if SOLUTION in r.text]
    assert not leaks, f"the solution appeared in: {leaks}"
    strange = {
        label: sorted(set(_keys(r.json())) - API_KEYS)
        for label, r, _ in walk
        if r.content and set(_keys(r.json())) - API_KEYS
    }
    assert not strange, f"keys the API does not define: {strange}"
    held = {GIVENS, "".join(wrong)}  # every grid the player's games held when looked at
    grids = {
        label: [(key, value) for key, value in _items(r.json()) if key in ("givens", "state")]
        for label, r, _ in walk
        if r.content
    }
    beyond = {
        label: bad
        for label, pairs in grids.items()
        if (bad := [k for k, v in pairs if v not in ({GIVENS} if k == "givens" else held)])
    }
    assert not beyond, f"grids the player does not have: {beyond}"
    by_label = {label: r for label, r, _ in walk}
    assert by_label["complete, wrong grid"].json() == {"correct": False, "submission_count": 1}
    # The parts of the walk that carry a grid, or a game past midnight, really did.
    assert by_label["start"].json()["state"] == GIVENS
    assert by_label["resume after a wrong submission"].json()["state"] == "".join(wrong)
    assert [g["game_id"] for g in by_label["today, a game continuing"].json()["continuing"]] == [
        game_id
    ]
