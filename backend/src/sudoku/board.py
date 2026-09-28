"""The board: 81 cells, the digits placed in them, and the candidates of the rest.

Grids travel as 81-character strings, read left to right and top to bottom,
``'1'``-``'9'`` for a digit and ``'0'`` for an empty cell (``DATA_MODEL.md``).
Inside the engine a grid is a list of 81 ints, 0 meaning empty.

Cells are numbered 0-80 row by row, so cell ``i`` sits in row ``i // 9`` and
column ``i % 9``. Every unit, peer set and index helper is computed once, here,
and everything else in the package uses these tables instead of redoing the
arithmetic.
"""

from collections.abc import Iterable, Sequence

DIGITS: tuple[int, ...] = tuple(range(1, 10))
CELLS: tuple[int, ...] = tuple(range(81))


def row_of(cell: int) -> int:
    return cell // 9


def col_of(cell: int) -> int:
    return cell % 9


def box_of(cell: int) -> int:
    """Boxes are numbered 0-8 row by row: 0 1 2 across the top, then 3 4 5."""
    return (cell // 27) * 3 + (cell % 9) // 3


ROWS: tuple[tuple[int, ...], ...] = tuple(
    tuple(c for c in CELLS if row_of(c) == r) for r in range(9)
)
COLS: tuple[tuple[int, ...], ...] = tuple(
    tuple(c for c in CELLS if col_of(c) == k) for k in range(9)
)
BOXES: tuple[tuple[int, ...], ...] = tuple(
    tuple(c for c in CELLS if box_of(c) == b) for b in range(9)
)
UNITS: tuple[tuple[int, ...], ...] = ROWS + COLS + BOXES
"""All 27 units. Rows first, then columns, then boxes — techniques scan in this
order, which makes their behaviour deterministic."""

PEERS: tuple[frozenset[int], ...] = tuple(
    frozenset(ROWS[row_of(c)] + COLS[col_of(c)] + BOXES[box_of(c)]) - {c} for c in CELLS
)
"""The 20 cells that share a unit with each cell: 8 in its row, 8 in its column,
and the 4 left over in its box."""


def parse_grid(text: str) -> list[int]:
    """Turn an 81-character grid string into a list of ints. Raises ``ValueError``."""
    if len(text) != 81 or not all(ch in "0123456789" for ch in text):
        raise ValueError("a grid is exactly 81 characters, each '0'-'9'")
    return [int(ch) for ch in text]


def format_grid(values: Sequence[int]) -> str:
    return "".join(str(v) for v in values)


def has_duplicate(values: Sequence[int]) -> bool:
    """True if some unit contains the same digit twice. Empty cells are ignored."""
    for unit in UNITS:
        placed = [values[c] for c in unit if values[c]]
        if len(placed) != len(set(placed)):
            return True
    return False


class Board:
    """A grid being solved: the digits placed so far and the candidates of every
    empty cell.

    ``candidates[c]`` is the set of digits cell ``c`` could still hold; for a
    filled cell it is empty. The two lists are kept consistent by ``place`` and
    ``eliminate``, which are the only two ways a technique changes a board.
    """

    __slots__ = ("candidates", "values")

    def __init__(self, values: list[int], candidates: list[set[int]]) -> None:
        if len(values) != 81 or len(candidates) != 81:
            raise ValueError("a board has 81 cells")
        self.values = values
        self.candidates = candidates

    @classmethod
    def from_string(cls, text: str) -> "Board":
        """Build a board from a grid string, with the candidates each empty cell
        has from its peers alone. Raises ``ValueError`` on a malformed grid or
        on givens that already break a rule."""
        values = parse_grid(text)
        if has_duplicate(values):
            raise ValueError("the givens repeat a digit within a unit")
        candidates = [
            set() if values[c] else set(DIGITS) - {values[p] for p in PEERS[c]} for c in CELLS
        ]
        return cls(values, candidates)

    def to_string(self) -> str:
        return format_grid(self.values)

    def copy(self) -> "Board":
        return Board(list(self.values), [set(s) for s in self.candidates])

    def is_solved(self) -> bool:
        return all(self.values)

    def is_broken(self) -> bool:
        """True if an empty cell has no candidate left: no solution from here."""
        return any(not self.values[c] and not self.candidates[c] for c in CELLS)

    def place(self, cell: int, digit: int) -> None:
        """Write ``digit`` into ``cell`` and remove it from every peer's candidates."""
        if self.values[cell]:
            raise ValueError(f"cell {cell} is already filled")
        if digit not in self.candidates[cell]:
            raise ValueError(f"{digit} is not a candidate of cell {cell}")
        self.values[cell] = digit
        self.candidates[cell] = set()
        for peer in PEERS[cell]:
            self.candidates[peer].discard(digit)

    def eliminate(self, cell: int, digit: int) -> bool:
        """Remove one candidate. Returns whether anything changed."""
        if digit in self.candidates[cell]:
            self.candidates[cell].remove(digit)
            return True
        return False

    def cells_with(self, unit: Iterable[int], digit: int) -> list[int]:
        """The cells of ``unit`` that still have ``digit`` as a candidate."""
        return [c for c in unit if digit in self.candidates[c]]
