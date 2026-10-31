"""Generating a puzzle of a requested difficulty.

The procedure of ``DIFFICULTY.md``:

1. Build a random complete, valid grid.
2. Visit the cells in random order. Empty each one, then ask the counting
   solver whether the grid still has exactly one solution. If it does, leave
   the cell empty; if not, put the digit back.
3. When every cell has been tried, the puzzle is *minimal*: no given can be
   removed without losing uniqueness. Grade it. Easy is the exception: it
   stops digging at a target drawn from ``EASY_CLUES``, so that it starts with
   32 to 42 givens (``DIFFICULTY.md``, "Clue ranges").
4. If the grade is the one requested, keep it. Otherwise throw the whole thing
   away and start again from step 1.
5. Medium and Hard then get givens back: cells of the solution, in random
   order, each kept only if the puzzle still grades the same, up to a target
   drawn from ``MEDIUM_CLUES`` or ``HARD_CLUES``. A Medium ends with 32 to 36
   givens and still needs a tier-2 technique, a Hard with 30 to 38 and a
   tier-3 one; random digging almost never stops on such a puzzle by itself.

Step 4 is a retry loop by design. Generation runs offline, days ahead of play,
so nobody waits on it. If Hard proves too slow to find, the fix is to bias the
digging or the starting grid — never to weaken the grader.

Everything random comes from one ``random.Random(seed)``, so a seed reproduces
its puzzle exactly — for the same ``GENERATOR_VERSION``. Change the algorithm
and old seeds give different puzzles, which is why puzzles are stored rather
than regenerated (``DECISIONS.md`` A1) and why the version is recorded with
each one.
"""

import random
from dataclasses import dataclass

from sudoku.board import CELLS, format_grid, parse_grid
from sudoku.grader import Grade, Tier, grade
from sudoku.solver import count_solutions, random_full_grid

GENERATOR_VERSION = "4"
"""1: every tier dug to minimal. 2: Easy stops at 32-42 givens.
3: Medium is refilled to 32-36 givens. 4: Hard is refilled to 30-38 givens."""

EASY_CLUES = range(32, 43)
"""How many givens an Easy puzzle starts with, inclusive of both ends."""

MEDIUM_CLUES = range(32, 37)
"""How many givens a Medium puzzle starts with, inclusive of both ends."""

HARD_CLUES = range(30, 39)
"""How many givens a Hard puzzle starts with, inclusive of both ends."""

CLUES = {Tier.EASY: EASY_CLUES, Tier.MEDIUM: MEDIUM_CLUES, Tier.HARD: HARD_CLUES}
"""How many givens each tier starts with."""


class GenerationError(RuntimeError):
    """No puzzle of the requested tier was found within the attempt budget."""


@dataclass(frozen=True)
class Puzzle:
    givens: str
    solution: str
    grade: Grade
    seed: int
    attempts: int
    """How many candidate puzzles were built before this one was accepted."""
    generator_version: str = GENERATOR_VERSION

    @property
    def clue_count(self) -> int:
        return sum(ch != "0" for ch in self.givens)


def dig(solution: str, rng: random.Random, keep: int = 0) -> str:
    """Remove givens from a full grid, in random order, for as long as the
    puzzle keeps exactly one solution, stopping once only ``keep`` are left.

    With ``keep=0`` the result is minimal: no given can be removed.
    """
    values = parse_grid(solution)
    order = list(CELLS)
    rng.shuffle(order)
    clues = len(CELLS)
    for cell in order:
        if clues <= keep:
            break
        kept = values[cell]
        values[cell] = 0
        if count_solutions(format_grid(values)) == 1:
            clues -= 1
        else:
            values[cell] = kept
    return format_grid(values)


def refill(givens: str, solution: str, rng: random.Random, tier: Tier, keep: int) -> str:
    """Give cells of ``solution`` back to ``givens``, in random order, keeping
    each only if the puzzle still grades ``tier``, until ``keep`` givens.

    A given added from the solution never costs uniqueness, only difficulty:
    the grade is what each one is checked against.
    """
    values, full = parse_grid(givens), parse_grid(solution)
    empty = [cell for cell in CELLS if values[cell] == 0]
    rng.shuffle(empty)
    clues = len(CELLS) - len(empty)
    for cell in empty:
        if clues >= keep:
            break
        values[cell] = full[cell]
        result = grade(format_grid(values))
        if result is not None and result.tier is tier:
            clues += 1
        else:
            values[cell] = 0
    return format_grid(values)


def generate(tier: Tier, seed: int, max_attempts: int = 2000) -> Puzzle:
    """A puzzle graded exactly ``tier``, with a unique solution.

    Raises ``GenerationError`` if ``max_attempts`` candidates are built and none
    of them grades as ``tier``.
    """
    rng = random.Random(seed)
    for attempt in range(1, max_attempts + 1):
        solution = random_full_grid(rng)
        keep = rng.choice(EASY_CLUES) if tier is Tier.EASY else 0
        givens = dig(solution, rng, keep)
        result = grade(givens)
        if result is None or result.tier is not tier:
            continue
        if tier is not Tier.EASY:
            givens = refill(givens, solution, rng, tier, rng.choice(CLUES[tier]))
            result = grade(givens)
        clues = sum(ch != "0" for ch in givens)
        if clues not in CLUES[tier]:
            continue
        if result is not None and result.tier is tier:
            return Puzzle(
                givens=givens, solution=solution, grade=result, seed=seed, attempts=attempt
            )
    raise GenerationError(f"no {tier.value} puzzle in {max_attempts} attempts (seed {seed})")
