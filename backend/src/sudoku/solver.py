"""The counting solver: does a grid have no solution, exactly one, or several?

This is deliberately *not* the grader. The grader (``grader.py``) solves the way
a person does, one named technique at a time, and gives up when the techniques
run out. This solver brute-forces: it guesses, and backtracks when a guess leads
nowhere. It is fast and it always finishes, which is exactly why it measures
nothing about difficulty — and exactly why it is the right tool to prove that a
puzzle has one solution. Two solvers, two jobs (``DIFFICULTY.md``).

How it searches: pick the empty cell with the fewest possible digits, try each
of them, recurse. Trying the most constrained cell first keeps the search tree
small. The digits used in each row, column and box are kept as bitmasks (bit
``d`` set means digit ``d`` is present), so "which digits can go here" is three
ORs instead of a walk over twenty peers.
"""

import random

from sudoku.board import CELLS, box_of, col_of, format_grid, has_duplicate, parse_grid, row_of

_ALL_DIGITS = 0b11_1111_1110  # bits 1..9
_ROW = tuple(row_of(c) for c in CELLS)
_COL = tuple(col_of(c) for c in CELLS)
_BOX = tuple(box_of(c) for c in CELLS)


class _Search:
    """One search over one grid. Holds the grid and its three sets of masks."""

    def __init__(self, values: list[int]) -> None:
        self.values = values
        self.rows = [0] * 9
        self.cols = [0] * 9
        self.boxes = [0] * 9
        for c in CELLS:
            if values[c]:
                self._set(c, values[c])
        self.solutions: list[str] = []

    def _set(self, cell: int, digit: int) -> None:
        bit = 1 << digit
        self.values[cell] = digit
        self.rows[_ROW[cell]] |= bit
        self.cols[_COL[cell]] |= bit
        self.boxes[_BOX[cell]] |= bit

    def _clear(self, cell: int, digit: int) -> None:
        bit = ~(1 << digit)
        self.values[cell] = 0
        self.rows[_ROW[cell]] &= bit
        self.cols[_COL[cell]] &= bit
        self.boxes[_BOX[cell]] &= bit

    def _options(self, cell: int) -> int:
        used = self.rows[_ROW[cell]] | self.cols[_COL[cell]] | self.boxes[_BOX[cell]]
        return _ALL_DIGITS & ~used

    def run(self, limit: int, rng: random.Random | None = None) -> int:
        """Count solutions, stopping once ``limit`` have been found. Keeps the
        first ``limit`` solutions in ``self.solutions``. With ``rng``, digits
        are tried in random order — that is how a random full grid is built."""
        best_cell = -1
        best_mask = 0
        best_count = 10
        for c in CELLS:
            if self.values[c]:
                continue
            mask = self._options(c)
            count = mask.bit_count()
            if count == 0:
                return 0  # a dead end: this cell can hold nothing
            if count < best_count:
                best_cell, best_mask, best_count = c, mask, count
                if count == 1:
                    break

        if best_cell == -1:  # no empty cell left: a solution
            self.solutions.append(format_grid(self.values))
            return 1

        digits = [d for d in range(1, 10) if best_mask >> d & 1]
        if rng is not None:
            rng.shuffle(digits)

        found = 0
        for d in digits:
            self._set(best_cell, d)
            found += self.run(limit - found, rng)
            self._clear(best_cell, d)
            if found >= limit:
                break
        return found


def count_solutions(grid: str, limit: int = 2) -> int:
    """How many solutions ``grid`` has, counting no further than ``limit``.

    The default of 2 is all uniqueness ever needs: 0 means broken, 1 means a
    valid puzzle, 2 means "more than one" — how many more does not matter, and
    counting them all can take a very long time on a sparse grid.
    """
    if limit < 1:
        raise ValueError("limit must be at least 1")
    values = parse_grid(grid)
    if has_duplicate(values):
        return 0
    return _Search(values).run(limit)


def unique_solution(grid: str) -> str | None:
    """The solution of ``grid`` if it has exactly one, otherwise ``None``."""
    values = parse_grid(grid)
    if has_duplicate(values):
        return None
    search = _Search(values)
    if search.run(2) != 1:
        return None
    return search.solutions[0]


def random_full_grid(rng: random.Random) -> str:
    """A complete, valid grid chosen at random: the search run on an empty grid,
    trying digits in random order and stopping at the first solution."""
    search = _Search([0] * 81)
    search.run(1, rng)
    return search.solutions[0]
