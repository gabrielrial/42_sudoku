"""Generating a puzzle of a requested difficulty.

The procedure of ``DIFFICULTY.md``:

1. Build a random complete, valid grid.
2. Visit the cells in random order. Empty each one, then ask the counting
   solver whether the grid still has exactly one solution. If it does, leave
   the cell empty; if not, put the digit back.
3. When every cell has been tried, the puzzle is *minimal*: no given can be
   removed without losing uniqueness. Grade it.
4. If the grade is the one requested, keep it. Otherwise throw the whole thing
   away and start again from step 1.

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

GENERATOR_VERSION = "1"


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


def dig(solution: str, rng: random.Random) -> str:
    """Remove givens from a full grid, in random order, for as long as the
    puzzle keeps exactly one solution. Returns a minimal puzzle."""
    values = parse_grid(solution)
    order = list(CELLS)
    rng.shuffle(order)
    for cell in order:
        kept = values[cell]
        values[cell] = 0
        if count_solutions(format_grid(values)) != 1:
            values[cell] = kept
    return format_grid(values)


def generate(tier: Tier, seed: int, max_attempts: int = 2000) -> Puzzle:
    """A puzzle graded exactly ``tier``, with a unique solution.

    Raises ``GenerationError`` if ``max_attempts`` candidates are built and none
    of them grades as ``tier``.
    """
    rng = random.Random(seed)
    for attempt in range(1, max_attempts + 1):
        solution = random_full_grid(rng)
        givens = dig(solution, rng)
        result = grade(givens)
        if result is not None and result.tier is tier:
            return Puzzle(
                givens=givens, solution=solution, grade=result, seed=seed, attempts=attempt
            )
    raise GenerationError(f"no {tier.value} puzzle in {max_attempts} attempts (seed {seed})")
