"""The solution never leaves the server (``AGENTS.md``, security floor; ``SECURITY.md``).

One test that walks every game endpoint, in every outcome a player can reach
before solving the puzzle, and looks for the solution in each answer. A
response model that one day grows a careless field fails here, whichever
endpoint it belongs to.

Once the player has solved the puzzle, their grid *is* the solution, and
showing it back to them leaks nothing; that state is deliberately not walked.
"""

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.database.models.game_sessions import GameSession
from tests.api.games import GAMES, GIVENS, SOLUTION, TODAY, start

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fixed_clock", "week")]


def test_no_answer_before_the_solve_contains_the_solution(
    db: Session, signed_in: TestClient
) -> None:
    answers: list[tuple[str, Response]] = []

    def call(label: str, response: Response) -> None:
        answers.append((label, response))

    call("today, nothing started", signed_in.get(TODAY))
    first = start(signed_in, "hard")
    call("start", first)
    game_id = first.json()["game_id"]
    call("start again (409)", start(signed_in, "hard"))
    call("today, started", signed_in.get(TODAY))
    call("resume", signed_in.get(f"{GAMES}/{game_id}"))
    empty = GIVENS.index("0")
    for digit in range(1, 10):  # the right digit among them
        call(
            f"input {digit}",
            signed_in.put(f"{GAMES}/{game_id}/cells/{empty}", json={"value": digit}),
        )
    given = next(i for i, ch in enumerate(GIVENS) if ch != "0")
    call(
        "input on a given (409)",
        signed_in.put(f"{GAMES}/{game_id}/cells/{given}", json={"value": 1}),
    )
    call("heartbeat", signed_in.post(f"{GAMES}/{game_id}/heartbeat"))
    call("complete, incomplete grid (409)", signed_in.post(f"{GAMES}/{game_id}/complete"))
    game = db.get(GameSession, game_id)
    assert game is not None
    wrong = list(SOLUTION)
    wrong[empty] = "1" if wrong[empty] != "1" else "2"
    game.state = "".join(wrong)
    db.commit()
    call("complete, wrong grid", signed_in.post(f"{GAMES}/{game_id}/complete"))
    call("resume after a wrong submission", signed_in.get(f"{GAMES}/{game_id}"))

    leaks = [label for label, response in answers if SOLUTION in response.text]
    assert not leaks, f"the solution appeared in: {leaks}"
    # And the walk really reached what it claims to have reached.
    assert [r.status_code for _, r in answers][:5] == [200, 201, 409, 200, 200]
    assert answers[-2][1].json() == {"correct": False, "submission_count": 1}
