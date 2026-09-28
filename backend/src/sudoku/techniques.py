"""The nine solving techniques of ``DIFFICULTY.md``, easiest first.

Every technique has the same shape: it takes a ``Board``, looks for **one**
instance of its pattern that actually changes something, applies it, and
returns ``True``. If no instance would change anything it leaves the board
untouched and returns ``False``.

"One instance" matters. The grader goes back to the easiest technique after
every success, so a hard technique only ever runs when every easier one is
stuck. If a technique applied all of its instances in one call, it would also do
work that an easier technique could have done after the first instance — and
the count of how often each technique fired would stop meaning anything.

A pattern that is present but eliminates nothing (a naked pair whose digits are
already gone from the rest of its unit, say) does not count as progress: the
technique keeps looking.

All scanning is in a fixed order — cells 0-80, units rows then columns then
boxes, digits 1-9 — so the same board always leads to the same step.
"""

from collections.abc import Callable
from itertools import combinations

from sudoku.board import (
    BOXES,
    CELLS,
    COLS,
    DIGITS,
    ROWS,
    UNITS,
    Board,
    box_of,
    col_of,
    row_of,
)

Technique = Callable[[Board], bool]


# --- Tier 1 ------------------------------------------------------------------


def naked_single(board: Board) -> bool:
    """A cell with exactly one candidate: place it."""
    for c in CELLS:
        if len(board.candidates[c]) == 1:
            (digit,) = board.candidates[c]
            board.place(c, digit)
            return True
    return False


def hidden_single(board: Board) -> bool:
    """A digit that fits in only one cell of a unit: place it there, whatever
    else that cell could hold."""
    for unit in UNITS:
        for d in DIGITS:
            cells = board.cells_with(unit, d)
            if len(cells) == 1:
                board.place(cells[0], d)
                return True
    return False


# --- Naked and hidden subsets (pairs in tier 2, triples in tier 3) ------------


def _naked_subset(board: Board, size: int) -> bool:
    """``size`` cells of one unit whose candidates, together, are only ``size``
    digits. Those digits must fill those cells, so no other cell of the unit can
    hold them.

    Each cell must have between 2 and ``size`` candidates: a cell with one
    candidate is a naked single, which is a different (easier) technique.
    """
    for unit in UNITS:
        pool = [c for c in unit if 2 <= len(board.candidates[c]) <= size]
        for group in combinations(pool, size):
            digits = set[int]().union(*(board.candidates[c] for c in group))
            if len(digits) != size:
                continue
            changed = False
            for c in unit:
                if c not in group:
                    for d in digits:
                        changed |= board.eliminate(c, d)
            if changed:
                return True
    return False


def _hidden_subset(board: Board, size: int) -> bool:
    """``size`` digits of one unit that, together, fit in only ``size`` cells.
    Those cells must hold those digits, so every other candidate goes from them.

    Each digit must fit in 2 to ``size`` cells: a digit with one place is a
    hidden single, which is a different (easier) technique.
    """
    for unit in UNITS:
        places = {d: board.cells_with(unit, d) for d in DIGITS}
        pool = [d for d in DIGITS if 2 <= len(places[d]) <= size]
        for group in combinations(pool, size):
            cells = set[int]().union(*(places[d] for d in group))
            if len(cells) != size:
                continue
            changed = False
            for c in sorted(cells):
                for d in sorted(board.candidates[c] - set(group)):
                    changed |= board.eliminate(c, d)
            if changed:
                return True
    return False


# --- Tier 2 ------------------------------------------------------------------


def naked_pair(board: Board) -> bool:
    return _naked_subset(board, 2)


def hidden_pair(board: Board) -> bool:
    return _hidden_subset(board, 2)


def pointing_pair(board: Board) -> bool:
    """Inside a box, every candidate for ``d`` lies in one row (or one column).
    ``d`` must go in that row inside this box, so it cannot go in the rest of
    the row."""
    for b, box in enumerate(BOXES):
        for d in DIGITS:
            cells = board.cells_with(box, d)
            if not cells:
                continue
            changed = False
            rows = {row_of(c) for c in cells}
            if len(rows) == 1:
                for c in ROWS[rows.pop()]:
                    if box_of(c) != b:
                        changed |= board.eliminate(c, d)
            cols = {col_of(c) for c in cells}
            if len(cols) == 1:
                for c in COLS[cols.pop()]:
                    if box_of(c) != b:
                        changed |= board.eliminate(c, d)
            if changed:
                return True
    return False


def box_line(board: Board) -> bool:
    """The mirror of the pointing pair. Inside a row (or column), every candidate
    for ``d`` lies in one box. ``d`` must go in that box on this line, so it
    cannot go in the rest of the box."""
    for line in ROWS + COLS:
        line_cells = set(line)
        for d in DIGITS:
            cells = board.cells_with(line, d)
            if not cells:
                continue
            boxes = {box_of(c) for c in cells}
            if len(boxes) != 1:
                continue
            changed = False
            for c in BOXES[boxes.pop()]:
                if c not in line_cells:
                    changed |= board.eliminate(c, d)
            if changed:
                return True
    return False


# --- Tier 3 ------------------------------------------------------------------


def naked_triple(board: Board) -> bool:
    return _naked_subset(board, 3)


def hidden_triple(board: Board) -> bool:
    return _hidden_subset(board, 3)


def x_wing(board: Board) -> bool:
    """``d`` fits in exactly two cells in each of two rows, and those cells are
    in the same two columns. Whichever way round ``d`` goes, it takes both
    columns, so it cannot go anywhere else in them. Then the same with rows and
    columns swapped."""
    for d in DIGITS:
        for base, cover, position in ((ROWS, COLS, col_of), (COLS, ROWS, row_of)):
            wings: list[tuple[int, frozenset[int]]] = []
            for index, line in enumerate(base):
                cells = board.cells_with(line, d)
                if len(cells) == 2:
                    wings.append((index, frozenset(position(c) for c in cells)))
            for (first, cross_a), (second, cross_b) in combinations(wings, 2):
                if cross_a != cross_b:
                    continue
                corners = set(base[first]) | set(base[second])
                changed = False
                for cross in sorted(cross_a):
                    for c in cover[cross]:
                        if c not in corners:
                            changed |= board.eliminate(c, d)
                if changed:
                    return True
    return False
