"""Each technique, isolated.

Every test starts from a blank board — all 81 cells empty, every candidate
possible — and carves exactly one pattern into the candidates by hand. A blank
board on its own triggers nothing, so whatever changes afterwards was caused by
the pattern. Each test also checks that the techniques *below* the one under
test find nothing on the same board: that is what "isolates" means here, and it
is what the grader's ladder relies on.

These boards are not real puzzles; they are the smallest candidate states that
contain one pattern. Whole puzzles are exercised in ``test_verification.py``.

Cell numbers: ``cell = row * 9 + column``, both from 0.
"""

from sudoku import techniques as t
from sudoku.board import BOXES, COLS, DIGITS, ROWS, Board

ALL = set(DIGITS)
LADDER_ORDER = [
    t.naked_single,
    t.hidden_single,
    t.naked_pair,
    t.hidden_pair,
    t.pointing_pair,
    t.box_line,
    t.naked_triple,
    t.hidden_triple,
    t.x_wing,
]


def blank() -> Board:
    return Board.from_string("0" * 81)


def remove(board: Board, cells, digits) -> None:
    for c in cells:
        for d in digits:
            board.eliminate(c, d)


def easier_than(technique):
    return LADDER_ORDER[: LADDER_ORDER.index(technique)]


def assert_isolated(board: Board, technique) -> None:
    """Nothing easier than ``technique`` makes progress on this board."""
    for easier in easier_than(technique):
        assert easier(board.copy()) is False, f"{easier.__name__} fired too"


def run_to_exhaustion(technique, board: Board) -> int:
    times = 0
    while technique(board):
        times += 1
    return times


def test_no_technique_fires_on_a_blank_board():
    for technique in LADDER_ORDER:
        assert technique(blank()) is False, technique.__name__


# --- Tier 1 ------------------------------------------------------------------


def test_naked_single_places_the_only_candidate():
    board = blank()
    board.candidates[40] = {5}
    assert t.naked_single(board) is True
    assert board.values[40] == 5
    assert 5 not in board.candidates[36]  # same row
    assert 5 not in board.candidates[4]  # same column
    assert 5 not in board.candidates[30]  # same box
    assert 5 in board.candidates[0]


def test_hidden_single_places_a_digit_with_one_home_even_among_other_candidates():
    board = blank()
    remove(board, [c for c in ROWS[0] if c != 3], [7])
    assert board.candidates[3] == ALL  # not a naked single
    assert_isolated(board, t.hidden_single)
    assert t.hidden_single(board) is True
    assert board.values[3] == 7


# --- Tier 2 ------------------------------------------------------------------


def test_naked_pair_clears_its_two_digits_from_the_rest_of_the_unit():
    board = blank()
    board.candidates[0] = {1, 2}
    board.candidates[4] = {1, 2}  # same row, different box
    assert_isolated(board, t.naked_pair)
    assert run_to_exhaustion(t.naked_pair, board) == 1
    for c in ROWS[0]:
        if c not in (0, 4):
            assert board.candidates[c] == ALL - {1, 2}
    assert board.candidates[9] == ALL  # other units untouched


def test_naked_pair_that_eliminates_nothing_is_not_progress():
    board = blank()
    board.candidates[0] = {1, 2}
    board.candidates[4] = {1, 2}
    remove(board, [c for c in ROWS[0] if c not in (0, 4)], [1, 2])
    assert t.naked_pair(board) is False


def test_hidden_pair_strips_the_other_candidates_from_its_two_cells():
    board = blank()
    remove(board, [c for c in ROWS[0] if c not in (2, 6)], [3, 8])
    assert_isolated(board, t.hidden_pair)
    assert t.hidden_pair(board) is True
    assert board.candidates[2] == {3, 8}
    assert board.candidates[6] == {3, 8}
    assert board.candidates[0] == ALL - {3, 8}


def test_pointing_pair_clears_the_rest_of_the_row():
    board = blank()
    # In box 0, digit 4 is left only in row 0.
    remove(board, [c for c in BOXES[0] if c not in ROWS[0]], [4])
    assert_isolated(board, t.pointing_pair)
    assert t.pointing_pair(board) is True
    assert all(4 not in board.candidates[c] for c in range(3, 9))
    assert all(4 in board.candidates[c] for c in (0, 1, 2, 12))


def test_pointing_pair_clears_the_rest_of_the_column():
    board = blank()
    # In box 8, digit 9 is left only in column 7.
    remove(board, [c for c in BOXES[8] if c not in COLS[7]], [9])
    assert_isolated(board, t.pointing_pair)
    assert run_to_exhaustion(t.pointing_pair, board) == 1
    assert all(9 not in board.candidates[r * 9 + 7] for r in range(6))
    assert all(9 in board.candidates[r * 9 + 7] for r in range(6, 9))


def test_box_line_reduction_clears_the_rest_of_the_box():
    board = blank()
    # In row 0, digit 6 is left only inside box 0.
    remove(board, range(3, 9), [6])
    assert_isolated(board, t.box_line)
    assert t.box_line(board) is True
    for c in BOXES[0]:
        assert (6 in board.candidates[c]) == (c in ROWS[0])


# --- Tier 3 ------------------------------------------------------------------


def test_naked_triple_with_no_cell_holding_all_three():
    board = blank()
    board.candidates[0] = {1, 2}
    board.candidates[3] = {2, 3}
    board.candidates[6] = {1, 3}
    assert_isolated(board, t.naked_triple)
    assert run_to_exhaustion(t.naked_triple, board) == 1
    for c in ROWS[0]:
        if c not in (0, 3, 6):
            assert board.candidates[c] == ALL - {1, 2, 3}


def test_naked_triple_with_one_cell_holding_all_three():
    board = blank()
    board.candidates[0] = {1, 2, 3}
    board.candidates[3] = {1, 2}
    board.candidates[6] = {2, 3}
    assert_isolated(board, t.naked_triple)
    assert t.naked_triple(board) is True
    assert board.candidates[8] == ALL - {1, 2, 3}


def test_hidden_triple_strips_the_other_candidates_from_its_three_cells():
    board = blank()
    remove(board, [c for c in ROWS[0] if c not in (1, 4, 7)], [4, 5, 6])
    assert_isolated(board, t.hidden_triple)
    assert t.hidden_triple(board) is True
    for c in (1, 4, 7):
        assert board.candidates[c] == {4, 5, 6}


def test_x_wing_on_rows_clears_the_two_columns():
    board = blank()
    # Digit 7 fits only in columns 2 and 6 in both row 1 and row 5.
    corners = {1 * 9 + 2, 1 * 9 + 6, 5 * 9 + 2, 5 * 9 + 6}
    remove(board, [c for c in ROWS[1] + ROWS[5] if c not in corners], [7])
    assert_isolated(board, t.x_wing)
    assert run_to_exhaustion(t.x_wing, board) == 1
    for c in COLS[2] + COLS[6]:
        assert (7 in board.candidates[c]) == (c in corners)
    assert 7 in board.candidates[0]


def test_x_wing_on_columns_clears_the_two_rows():
    board = blank()
    # Digit 2 fits only in rows 3 and 7 in both column 0 and column 8.
    corners = {3 * 9 + 0, 3 * 9 + 8, 7 * 9 + 0, 7 * 9 + 8}
    remove(board, [c for c in COLS[0] + COLS[8] if c not in corners], [2])
    assert_isolated(board, t.x_wing)
    assert run_to_exhaustion(t.x_wing, board) == 1
    for c in ROWS[3] + ROWS[7]:
        assert (2 in board.candidates[c]) == (c in corners)


def test_x_wing_that_eliminates_nothing_is_not_progress():
    board = blank()
    corners = {1 * 9 + 2, 1 * 9 + 6, 5 * 9 + 2, 5 * 9 + 6}
    remove(board, [c for c in ROWS[1] + ROWS[5] if c not in corners], [7])
    remove(board, [c for c in COLS[2] + COLS[6] if c not in corners], [7])
    assert t.x_wing(board) is False


# --- Subsets do not do a single's work ----------------------------------------


def test_naked_pair_ignores_a_cell_that_is_already_a_naked_single():
    board = blank()
    board.candidates[0] = {1}
    board.candidates[4] = {1, 2}
    assert t.naked_pair(board) is False


def test_hidden_pair_ignores_a_digit_that_is_already_a_hidden_single():
    board = blank()
    remove(board, [c for c in ROWS[0] if c != 0], [5])  # 5: one place in row 0
    remove(board, [c for c in ROWS[0] if c not in (0, 1)], [6])  # 6: two places
    assert t.hidden_pair(board) is False
