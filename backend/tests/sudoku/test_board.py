import pytest

from sudoku.board import (
    BOXES,
    CELLS,
    COLS,
    PEERS,
    ROWS,
    UNITS,
    Board,
    box_of,
    format_grid,
    has_duplicate,
    parse_grid,
)

EMPTY = "0" * 81


def test_there_are_27_units_of_nine_cells_covering_the_grid():
    assert len(UNITS) == 27
    assert all(len(unit) == 9 for unit in UNITS)
    for group in (ROWS, COLS, BOXES):
        assert sorted(c for unit in group for c in unit) == list(CELLS)


def test_boxes_are_numbered_row_by_row():
    assert BOXES[0] == (0, 1, 2, 9, 10, 11, 18, 19, 20)
    assert box_of(80) == 8
    assert box_of(8) == 2
    assert box_of(27) == 3


def test_every_cell_has_twenty_peers_and_is_not_its_own_peer():
    for c in CELLS:
        assert len(PEERS[c]) == 20
        assert c not in PEERS[c]
    assert PEERS[0] >= {1, 8, 9, 72, 10, 20}
    assert 30 not in PEERS[0]


@pytest.mark.parametrize("bad", ["", "0" * 80, "0" * 82, "0" * 80 + ".", "0" * 80 + "a"])
def test_malformed_grids_are_rejected(bad):
    with pytest.raises(ValueError):
        parse_grid(bad)


def test_parse_and_format_round_trip():
    text = "123456789" + "0" * 72
    assert format_grid(parse_grid(text)) == text


def test_duplicates_are_found_in_rows_columns_and_boxes():
    assert not has_duplicate(parse_grid(EMPTY))
    row = "11" + "0" * 79
    col = "1" + "0" * 8 + "1" + "0" * 71
    box = "1" + "0" * 9 + "1" + "0" * 70
    assert has_duplicate(parse_grid(row))
    assert has_duplicate(parse_grid(col))
    assert has_duplicate(parse_grid(box))


def test_givens_that_break_a_rule_are_refused():
    with pytest.raises(ValueError):
        Board.from_string("55" + "0" * 79)


def test_candidates_come_from_the_peers():
    board = Board.from_string("123000000" + "0" * 72)
    assert board.candidates[0] == set()
    assert board.candidates[3] == {4, 5, 6, 7, 8, 9}
    assert board.candidates[9] == {4, 5, 6, 7, 8, 9}  # same box as 1, 2, 3
    assert board.candidates[12] == set(range(1, 10))  # shares nothing with them


def test_place_writes_the_digit_and_removes_it_from_every_peer():
    board = Board.from_string(EMPTY)
    board.place(40, 5)
    assert board.values[40] == 5
    assert board.candidates[40] == set()
    assert all(5 not in board.candidates[p] for p in PEERS[40])
    assert 5 in board.candidates[0]


def test_place_refuses_a_filled_cell_or_a_non_candidate():
    board = Board.from_string("1" + "0" * 80)
    with pytest.raises(ValueError):
        board.place(0, 2)
    with pytest.raises(ValueError):
        board.place(1, 1)


def test_eliminate_reports_whether_it_changed_anything():
    board = Board.from_string(EMPTY)
    assert board.eliminate(0, 3) is True
    assert board.eliminate(0, 3) is False


def test_a_cell_with_no_candidate_breaks_the_board():
    board = Board.from_string(EMPTY)
    assert not board.is_broken()
    board.candidates[0] = set()
    assert board.is_broken()


def test_copy_is_independent():
    board = Board.from_string(EMPTY)
    other = board.copy()
    other.place(0, 1)
    assert board.values[0] == 0
    assert 1 in board.candidates[1]
