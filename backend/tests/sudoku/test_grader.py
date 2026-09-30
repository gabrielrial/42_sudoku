import inspect
from unittest.mock import patch

import pytest

from sudoku import grader
from sudoku.board import Board
from sudoku.grader import LADDER, Step, Tier, grade, solve

FULL = "".join("".join(str((r * 3 + r // 3 + c) % 9 + 1) for c in range(9)) for r in range(9))


def test_the_ladder_is_the_one_in_the_specification():
    assert [step.name for step in LADDER] == [
        "naked_single",
        "hidden_single",
        "naked_pair",
        "hidden_pair",
        "pointing_pair",
        "box_line",
        "naked_triple",
        "hidden_triple",
        "x_wing",
    ]
    assert [step.tier for step in LADDER] == [Tier.EASY] * 2 + [Tier.MEDIUM] * 4 + [Tier.HARD] * 3


def test_tier_values_match_the_api_difficulties():
    assert [t.value for t in Tier] == ["easy", "medium", "hard"]


def test_the_ladder_restarts_from_the_top_after_every_success():
    """The load-bearing ``break``. A fake two-step ladder: the hard step fills
    cell 0; only then can the easy step fill cell 1. If the grader carried on
    down the ladder instead of restarting, the easy step would never be retried
    and the solve would stall."""
    calls: list[str] = []

    def easy(board: Board) -> bool:
        calls.append("easy")
        if board.values[0] and not board.values[1]:
            board.place(1, int(FULL[1]))
            return True
        return False

    def hard(board: Board) -> bool:
        calls.append("hard")
        if not board.values[0]:
            board.place(0, int(FULL[0]))
            return True
        return False

    ladder = (Step("easy", Tier.EASY, easy), Step("hard", Tier.HARD, hard))
    with patch.object(grader, "LADDER", ladder):
        result = grade("00" + FULL[2:])

    assert calls == ["easy", "hard", "easy"]
    assert result is not None
    assert result.tier is Tier.HARD
    assert result.hardest == "hard"
    assert result.counts == {"easy": 1, "hard": 1}


def test_a_puzzle_the_ladder_cannot_finish_is_discarded_not_graded_hard():
    def never(board: Board) -> bool:
        return False

    with patch.object(grader, "LADDER", (Step("never", Tier.HARD, never),)):
        assert grade("0" + FULL[1:]) is None


def test_a_puzzle_with_several_solutions_is_discarded():
    # A near-empty grid: the ladder stalls long before it could finish.
    assert grade("1" + "0" * 80) is None


def test_one_missing_digit_is_easy_and_needs_only_a_naked_single():
    result = solve("0" + FULL[1:])
    assert result is not None
    grid, g = result
    assert grid == FULL
    assert g.tier is Tier.EASY
    assert g.hardest == "naked_single"
    assert g.counts["naked_single"] == 1
    assert sum(g.counts.values()) == 1


def test_every_technique_is_listed_in_the_counts():
    g = grade("0" + FULL[1:])
    assert g is not None
    assert set(g.counts) == {step.name for step in LADDER}


@pytest.mark.parametrize("bad", ["0" * 80, "11" + "0" * 79])
def test_malformed_or_rule_breaking_givens_are_an_error(bad):
    with pytest.raises(ValueError):
        grade(bad)


def test_a_full_grid_is_an_error_not_a_grade():
    with pytest.raises(ValueError):
        grade(FULL)


def test_the_grader_takes_the_givens_and_nothing_else():
    """Structural proof that the grader cannot peek: there is no parameter
    through which a solution could reach it."""
    assert list(inspect.signature(grade).parameters) == ["givens"]
    assert list(inspect.signature(solve).parameters) == ["givens"]
