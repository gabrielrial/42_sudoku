"""``ensure_puzzles``: the daily puzzles exist ahead of time (``app/services/puzzles.py``).

Generating a real Hard takes about 16 seconds, so the tests do not generate per
call. ``Maker`` hands out real puzzles, generated once per run from seeds that
are known to be quick, and records what it was asked for. It can also be told
to fail, or to hand out a puzzle that does not verify.
"""

import dataclasses
import logging
from collections.abc import Iterator
from datetime import date, timedelta
from functools import cache

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models.puzzles import Puzzle, PuzzleSolution
from app.services import puzzles as service
from app.services.puzzles import ensure_puzzles
from sudoku.generator import GenerationError, generate
from sudoku.generator import Puzzle as GeneratedPuzzle
from sudoku.grader import Tier
from sudoku.solver import count_solutions

pytestmark = pytest.mark.db

QUICK_SEEDS = {Tier.EASY: 0, Tier.MEDIUM: 0, Tier.HARD: 5}
START = date(2026, 10, 24)  # a week across the end of summer time: dates do not care


@cache
def _real(tier: Tier) -> GeneratedPuzzle:
    return generate(tier, QUICK_SEEDS[tier])


class Maker:
    """Stands in for ``sudoku.generator.generate``."""

    def __init__(self) -> None:
        self.calls: list[tuple[Tier, int]] = []
        self.failures: dict[Tier, int] = {}
        """How many more calls for that tier raise GenerationError."""
        self.broken: dict[Tier, int] = {}
        """How many more calls for that tier return a puzzle with two solutions."""

    def __call__(self, tier: Tier, seed: int) -> GeneratedPuzzle:
        self.calls.append((tier, seed))
        if self.failures.get(tier, 0):
            self.failures[tier] -= 1
            raise GenerationError(f"no {tier.value} puzzle (seed {seed})")
        puzzle = dataclasses.replace(_real(tier), seed=seed)
        if self.broken.get(tier, 0):
            self.broken[tier] -= 1
            first_given = next(i for i, ch in enumerate(puzzle.givens) if ch != "0")
            # Minimal puzzles lose uniqueness with any given removed.
            givens = puzzle.givens[:first_given] + "0" + puzzle.givens[first_given + 1 :]
            puzzle = dataclasses.replace(puzzle, givens=givens)
        return puzzle


@pytest.fixture
def maker() -> Maker:
    return Maker()


def _seeds() -> Iterator[int]:
    n = 100
    while True:
        n += 1
        yield n


def _ensure(db: Session, maker: Maker, days: int = 7, start: date = START) -> service.Report:
    seeds = _seeds()
    return ensure_puzzles(db, start, days, make=maker, seed=lambda: next(seeds))


def _count(db: Session, model: type[Puzzle] | type[PuzzleSolution]) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def _stored(db: Session) -> list[tuple[date, str]]:
    rows = db.execute(select(Puzzle.puzzle_date, Puzzle.difficulty).order_by(Puzzle.id))
    return [(day, difficulty) for day, difficulty in rows]


# --- filling the week ----------------------------------------------------------------------


def test_every_day_gets_its_three_puzzles(db: Session, maker: Maker) -> None:
    report = _ensure(db, maker)

    days = [START + timedelta(days=n) for n in range(7)]
    expected = [(day, tier) for day in days for tier in Tier]
    assert report.created == expected
    assert report.failed == []
    assert _stored(db) == [(day, tier.value) for day, tier in expected]


def test_the_earliest_day_comes_first(db: Session, maker: Maker) -> None:
    # Today is the one a player may need any minute; next week can wait.
    report = _ensure(db, maker)

    assert report.created[:3] == [(START, Tier.EASY), (START, Tier.MEDIUM), (START, Tier.HARD)]


def test_each_puzzle_is_stored_as_generated(db: Session, maker: Maker) -> None:
    _ensure(db, maker, days=1)

    row = db.scalar(select(Puzzle).where(Puzzle.difficulty == "hard"))
    assert row is not None
    generated = _real(Tier.HARD)
    assert row.givens == generated.givens
    assert row.clue_count == generated.clue_count
    assert row.hardest_technique == generated.grade.hardest
    assert row.technique_counts == generated.grade.counts
    assert row.generator_version == generated.generator_version
    hard_seed = next(s for t, s in maker.calls if t is Tier.HARD)
    assert row.seed == hard_seed  # the seed it was made from


def test_each_puzzle_has_its_solution_beside_it(db: Session, maker: Maker) -> None:
    _ensure(db, maker, days=2)

    pairs = db.execute(
        select(Puzzle.givens, PuzzleSolution.solution).join(
            PuzzleSolution, PuzzleSolution.puzzle_id == Puzzle.id
        )
    ).all()
    assert len(pairs) == 6
    for givens, solution in pairs:
        assert count_solutions(givens) == 1
        assert all(g in ("0", s) for g, s in zip(givens, solution, strict=True))


# --- idempotent: what exists is left alone ---------------------------------------------------


def test_a_second_run_creates_nothing_and_generates_nothing(db: Session, maker: Maker) -> None:
    _ensure(db, maker)
    maker.calls.clear()

    report = _ensure(db, maker)

    assert report.created == []
    assert maker.calls == []
    assert _count(db, Puzzle) == 21


def test_only_what_is_missing_is_generated(db: Session, maker: Maker) -> None:
    _ensure(db, maker, days=1)
    medium = db.scalar(select(Puzzle).where(Puzzle.difficulty == "medium"))
    db.delete(medium)
    db.commit()
    maker.calls.clear()

    report = _ensure(db, maker, days=2)

    assert report.created == [
        (START, Tier.MEDIUM),
        *[(START + timedelta(days=1), tier) for tier in Tier],
    ]


def test_tomorrow_the_window_moves_by_one_day(db: Session, maker: Maker) -> None:
    _ensure(db, maker)

    report = _ensure(db, maker, start=START + timedelta(days=1))

    assert report.created == [(START + timedelta(days=7), tier) for tier in Tier]


def test_a_puzzle_stored_by_another_run_meanwhile_is_not_an_error(
    db: Session, maker: Maker, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Two runs at once (the service, and someone running the command by hand):
    # both see the day missing, one stores first, the unique constraint stops
    # the other. Simulated by a run that cannot see what is already there.
    _ensure(db, maker, days=1)
    monkeypatch.setattr(service, "_exists", lambda *_: False)

    report = _ensure(db, maker, days=1)

    assert report.created == []
    assert _count(db, Puzzle) == 3
    assert _count(db, PuzzleSolution) == 3


# --- when generation fails ------------------------------------------------------------------


def test_a_failed_generation_is_retried_with_another_seed(db: Session, maker: Maker) -> None:
    maker.failures[Tier.HARD] = 2

    report = _ensure(db, maker, days=1)

    assert (START, Tier.HARD) in report.created
    hard_seeds = [s for t, s in maker.calls if t is Tier.HARD]
    assert len(hard_seeds) == 3
    assert len(set(hard_seeds)) == 3


def test_a_puzzle_that_cannot_be_made_is_reported_and_the_rest_go_on(
    db: Session, maker: Maker, caplog: pytest.LogCaptureFixture
) -> None:
    maker.failures[Tier.HARD] = service.TRIES  # every seed of the first Hard fails

    with caplog.at_level(logging.WARNING, logger="app.services.puzzles"):
        report = _ensure(db, maker, days=2)

    assert report.failed == [(START, Tier.HARD)]
    assert len(report.created) == 5  # the other two of day one, all three of day two
    assert f"no hard puzzle for {START}" in caplog.text


def test_a_puzzle_that_fails_verification_is_never_stored(
    db: Session, maker: Maker, caplog: pytest.LogCaptureFixture
) -> None:
    maker.broken[Tier.EASY] = 1

    with caplog.at_level(logging.ERROR, logger="app.services.puzzles"):
        report = _ensure(db, maker, days=1)

    assert (START, Tier.EASY) in report.created  # with the next seed
    easy = db.scalar(select(Puzzle).where(Puzzle.difficulty == "easy"))
    assert easy is not None
    assert count_solutions(easy.givens) == 1
    assert "failed verification" in caplog.text


def test_a_puzzle_of_the_wrong_tier_is_never_stored(db: Session, maker: Maker) -> None:
    def wrong_tier(tier: Tier, seed: int) -> GeneratedPuzzle:
        return dataclasses.replace(_real(Tier.EASY), seed=seed)  # asked for Hard, gets Easy

    report = ensure_puzzles(db, START, 1, make=wrong_tier, seed=lambda: 1)

    assert report.created == [(START, Tier.EASY)]
    assert report.failed == [(START, Tier.MEDIUM), (START, Tier.HARD)]


def test_no_days_means_nothing_to_do(db: Session, maker: Maker) -> None:
    assert _ensure(db, maker, days=0) == service.Report()
    assert maker.calls == []
