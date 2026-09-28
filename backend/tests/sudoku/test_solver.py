import random

import pytest

from sudoku.board import has_duplicate, parse_grid
from sudoku.solver import count_solutions, random_full_grid, unique_solution

EMPTY = "0" * 81
# A valid complete grid: each row is the one above shifted by 3 (or by 1 at
# each band), which satisfies every row, column and box.
FULL = "".join(
    "".join(str((r * 3 + r // 3 + c) % 9 + 1) for c in range(9)) for r in range(9)
)


def test_the_reference_full_grid_is_valid():
    assert not has_duplicate(parse_grid(FULL))
    assert "0" not in FULL


def test_a_full_valid_grid_has_one_solution():
    assert count_solutions(FULL) == 1
    assert unique_solution(FULL) == FULL


def test_counting_stops_at_the_limit():
    assert count_solutions(EMPTY) == 2
    assert count_solutions(EMPTY, limit=1) == 1
    assert count_solutions(EMPTY, limit=5) == 5


def test_limit_must_be_positive():
    with pytest.raises(ValueError):
        count_solutions(EMPTY, limit=0)


def test_one_missing_digit_is_still_unique():
    grid = "0" + FULL[1:]
    assert count_solutions(grid) == 1
    assert unique_solution(grid) == FULL


def test_a_sparse_grid_has_several_solutions():
    grid = "1" + "0" * 80
    assert count_solutions(grid) == 2
    assert unique_solution(grid) is None


def test_givens_that_break_a_rule_have_no_solution():
    assert count_solutions("11" + "0" * 79) == 0
    assert unique_solution("11" + "0" * 79) is None


def test_a_cell_with_nowhere_to_go_has_no_solution():
    # Row 0 holds 1-8 in cells 1-8, and 9 sits lower in column 0: cell 0 is dead.
    grid = "012345678" + "9" + "0" * 71
    assert not has_duplicate(parse_grid(grid))
    assert count_solutions(grid) == 0


def test_random_full_grids_are_valid_and_reproducible():
    first = random_full_grid(random.Random(42))
    assert "0" not in first
    assert not has_duplicate(parse_grid(first))
    assert random_full_grid(random.Random(42)) == first
    assert random_full_grid(random.Random(43)) != first
