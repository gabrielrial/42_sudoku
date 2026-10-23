"""``python -m app.jobs.generate_puzzles``: the command the ``puzzles`` service runs.

What the command itself decides: which day is "today", how many days, the exit
status, and the loop. ``ensure_puzzles`` is tested on its own
(``tests/services/test_puzzles.py``), so here it is replaced by a recorder, and
no database is needed.
"""

import logging
from datetime import date, datetime

import pytest

from app import clock
from app.config import get_settings
from app.jobs import generate_puzzles as job
from app.services.puzzles import Report
from sudoku.grader import Tier


class Calls:
    def __init__(self) -> None:
        self.made: list[tuple[date, int]] = []
        self.answers: list[Report | Exception] = []
        """What each round answers, in order; then an empty report."""

    def __call__(self, db: object, start: date, days: int) -> Report:
        self.made.append((start, days))
        answer = self.answers.pop(0) if self.answers else Report()
        if isinstance(answer, Exception):
            raise answer
        return answer


class _NoSession:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, *_: object) -> None:
        return None


class Stop(Exception):
    """Ends a loop that would otherwise never return."""


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> Calls:
    recorder = Calls()
    monkeypatch.setattr(job, "ensure_puzzles", recorder)
    monkeypatch.setattr(job, "SessionFactory", _NoSession)
    return recorder


def _at(monkeypatch: pytest.MonkeyPatch, instant: datetime) -> None:
    monkeypatch.setattr(clock, "now", lambda: instant)


def _sleeper(rounds: int) -> tuple[list[float], object]:
    """A ``sleep`` that records each wait and stops the loop after ``rounds``."""
    waits: list[float] = []

    def sleep(seconds: float) -> None:
        waits.append(seconds)
        if len(waits) == rounds:
            raise Stop

    return waits, sleep


# --- one round -----------------------------------------------------------------------------


def test_today_is_the_berlin_day(calls: Calls, monkeypatch: pytest.MonkeyPatch) -> None:
    # 22:30 UTC on 24 October is already 00:30 on 25 October in Berlin, the
    # night summer time ends.
    _at(monkeypatch, datetime(2026, 10, 24, 22, 30, tzinfo=clock.UTC))

    job.main([])

    assert calls.made[0][0] == date(2026, 10, 25)


def test_the_days_come_from_the_settings(calls: Calls) -> None:
    job.main([])

    assert calls.made[0][1] == get_settings().puzzle_days_ahead == 7


def test_days_can_be_given(calls: Calls) -> None:
    job.main(["--days", "2"])

    assert calls.made[0][1] == 2


@pytest.mark.parametrize("argv", [["--days", "0"], ["--days", "-1"], ["--every", "0"]])
def test_nonsense_is_refused(calls: Calls, argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        job.main(argv)

    assert exc.value.code == 2
    assert calls.made == []


def test_nothing_missing_exits_0(calls: Calls) -> None:
    calls.answers = [Report(created=[(date(2026, 10, 25), Tier.EASY)])]

    assert job.main([]) == 0


def test_a_puzzle_that_could_not_be_made_exits_1(calls: Calls) -> None:
    calls.answers = [Report(failed=[(date(2026, 10, 25), Tier.HARD)])]

    assert job.main([]) == 1


def test_a_round_says_what_it_did(calls: Calls, caplog: pytest.LogCaptureFixture) -> None:
    calls.answers = [Report(created=[(date(2026, 10, 25), Tier.EASY)] * 2)]

    with caplog.at_level(logging.INFO, logger="app.jobs.generate_puzzles"):
        job.main(["--days", "3"])

    assert "for 3 days: 2 created, 0 failed" in caplog.text


# --- the service: again and again ----------------------------------------------------------


def test_every_repeats_at_that_interval(calls: Calls) -> None:
    waits, sleep = _sleeper(rounds=3)

    with pytest.raises(Stop):
        job.main(["--every", "3600"], sleep=sleep)  # type: ignore[arg-type]

    assert len(calls.made) == 3
    assert waits == [3600, 3600, 3600]


def test_a_round_that_fails_outright_is_retried_sooner(
    calls: Calls, caplog: pytest.LogCaptureFixture
) -> None:
    # The service can start before the tables exist (make all migrates after
    # starting it): that round fails, and the next comes a minute later.
    calls.answers = [RuntimeError("relation puzzles does not exist")]
    waits, sleep = _sleeper(rounds=2)

    with caplog.at_level(logging.ERROR, logger="app.jobs.generate_puzzles"), pytest.raises(Stop):
        job.main(["--every", "3600"], sleep=sleep)  # type: ignore[arg-type]

    assert waits == [job.RETRY_AFTER_ERROR, 3600]
    assert len(calls.made) == 2
    assert "puzzle round failed" in caplog.text
