"""Making sure the daily puzzles exist ahead of time (``DECISIONS.md`` A1, Q11).

Puzzles are generated days before they are played and stored with their
solution; they are never regenerated and never change. ``ensure_puzzles``
fills whatever is missing from a range of days and leaves the rest alone, so
running it twice, or from two places at once, is harmless.

Every puzzle is checked again before it is stored: the counting solver must
find exactly one solution, and it must be the generator's (``DIFFICULTY.md``:
"verified independently of the generator that produced it").
"""

import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models.puzzles import Puzzle, PuzzleSolution
from sudoku.generator import GenerationError, generate
from sudoku.generator import Puzzle as GeneratedPuzzle
from sudoku.grader import Tier
from sudoku.solver import unique_solution

logger = logging.getLogger(__name__)

Generate = Callable[[Tier, int], GeneratedPuzzle]

TRIES = 3
"""Seeds tried for one puzzle before that day and difficulty is reported as
failed. One seed already runs the generator's whole attempt budget, so three in
a row failing means something is wrong, not unlucky."""


def new_seed() -> int:
    """A random seed, recorded with the puzzle for traceability (it fits ``BIGINT``)."""
    return secrets.randbelow(2**32)


@dataclass
class Report:
    created: list[tuple[date, Tier]] = field(default_factory=list)
    failed: list[tuple[date, Tier]] = field(default_factory=list)


def ensure_puzzles(
    db: Session,
    start: date,
    days: int,
    *,
    make: Generate = generate,
    seed: Callable[[], int] = new_seed,
) -> Report:
    """Generate and store every puzzle missing from ``start`` and the ``days - 1``
    days after it, earliest day first, Easy to Hard.

    Each puzzle is committed as soon as it is stored, so an interrupted run
    keeps what it finished. A puzzle that cannot be generated is logged and
    reported; the others still are. ``make`` and ``seed`` exist for the tests.
    """
    report = Report()
    for offset in range(days):
        day = start + timedelta(days=offset)
        for tier in Tier:
            if _exists(db, day, tier):
                continue
            puzzle = _generate(tier, make, seed)
            if puzzle is None:
                logger.warning("no %s puzzle for %s after %d seeds", tier.value, day, TRIES)
                report.failed.append((day, tier))
            elif _store(db, day, puzzle):
                logger.info("stored the %s puzzle for %s (seed %d)", tier.value, day, puzzle.seed)
                report.created.append((day, tier))
    return report


def _exists(db: Session, day: date, tier: Tier) -> bool:
    found = db.scalar(
        select(Puzzle.id).where(Puzzle.puzzle_date == day, Puzzle.difficulty == tier.value)
    )
    return found is not None


def _generate(tier: Tier, make: Generate, seed: Callable[[], int]) -> GeneratedPuzzle | None:
    """A verified puzzle of ``tier``, or ``None`` after ``TRIES`` seeds."""
    for _ in range(TRIES):
        try:
            puzzle = make(tier, seed())
        except GenerationError as exc:
            logger.warning("%s", exc)
            continue
        if puzzle.grade.tier is not tier or unique_solution(puzzle.givens) != puzzle.solution:
            # The generator promised this tier and one solution; the check
            # disagrees. A bug, not bad luck: never store it, and say so loudly.
            logger.error(
                "generated %s puzzle failed verification (seed %d)", tier.value, puzzle.seed
            )
            continue
        return puzzle
    return None


def _store(db: Session, day: date, puzzle: GeneratedPuzzle) -> bool:
    """Store one puzzle with its solution. ``False`` if that day and difficulty
    were stored meanwhile by another run: the unique constraint decides."""
    row = Puzzle(
        puzzle_date=day,
        difficulty=puzzle.grade.tier.value,
        givens=puzzle.givens,
        clue_count=puzzle.clue_count,
        hardest_technique=puzzle.grade.hardest,
        technique_counts=dict(puzzle.grade.counts),
        generator_version=puzzle.generator_version,
        seed=puzzle.seed,
    )
    try:
        db.add(row)
        db.flush()  # gives the row its id, for the solution
        db.add(PuzzleSolution(puzzle_id=row.id, solution=puzzle.solution))
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.info("the %s puzzle for %s was stored by another run", puzzle.grade.tier.value, day)
        return False
    return True
