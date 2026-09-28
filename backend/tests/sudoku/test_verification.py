"""The verification requirements of ``DIFFICULTY.md``, one section each.

A broken grader fails silently: three tiers that all feel the same, and nobody
notices for weeks. These tests are how it fails loudly instead.
"""

import random
from functools import cache

import pytest

from sudoku.board import Board
from sudoku.generator import dig, generate
from sudoku.grader import LADDER, Tier, grade, solve
from sudoku.solver import count_solutions, random_full_grid, unique_solution

_generated = cache(generate)
"""Generation is deterministic per seed, so each puzzle is built once per run."""

TIER_OF = {step.name: step.tier for step in LADDER}
EASY_SEEDS = range(20)
MEDIUM_SEEDS = range(6)
# Chosen because they are found quickly; between them they cover a triple and
# an X-Wing as the hardest technique. Regenerating costs seconds, not minutes.
HARD_SEEDS = (5, 4)


def _fired(counts: dict[str, int], tier: Tier) -> int:
    return sum(n for name, n in counts.items() if TIER_OF[name] is tier)


# --- Every technique is sound -------------------------------------------------


def test_no_technique_ever_removes_the_true_digit():
    """The strongest check on the techniques: solve many real puzzles step by
    step and, after every single step, compare the board with the known answer.
    A placed digit must be the right one, and the right digit must still be a
    candidate of every empty cell. One wrong elimination anywhere fails this.

    The test knows the answer. The grader does not: it is driven here only
    through ``Step.apply``, exactly as ``solve`` drives it.
    """
    rng = random.Random(2026)
    steps = 0
    for _ in range(60):
        answer = random_full_grid(rng)
        board = Board.from_string(dig(answer, rng))
        while not board.is_solved():
            step = next((s for s in LADDER if s.apply(board)), None)
            if step is None:
                break  # beyond tier 3: discarded, but everything so far was checked
            steps += 1
            for c in range(81):
                if board.values[c]:
                    assert board.values[c] == int(answer[c]), f"{step.name} placed wrong"
                else:
                    assert int(answer[c]) in board.candidates[c], f"{step.name} was unsound"
    assert steps > 1000  # the test really exercised something


# --- Generated puzzles get the tier they were asked for -----------------------


@pytest.mark.parametrize("seed", EASY_SEEDS)
def test_every_generated_easy_puzzle_is_solved_by_singles_alone(seed):
    puzzle = _generated(Tier.EASY, seed)
    assert puzzle.grade.tier is Tier.EASY
    assert _fired(puzzle.grade.counts, Tier.MEDIUM) == 0
    assert _fired(puzzle.grade.counts, Tier.HARD) == 0


@pytest.mark.parametrize("seed", MEDIUM_SEEDS)
def test_every_generated_medium_puzzle_needs_tier_2_and_nothing_harder(seed):
    puzzle = _generated(Tier.MEDIUM, seed)
    assert _fired(puzzle.grade.counts, Tier.MEDIUM) >= 1
    assert _fired(puzzle.grade.counts, Tier.HARD) == 0


@pytest.mark.parametrize("seed", HARD_SEEDS)
def test_every_generated_hard_puzzle_needs_tier_3(seed):
    puzzle = _generated(Tier.HARD, seed)
    assert _fired(puzzle.grade.counts, Tier.HARD) >= 1


def test_hard_seeds_cover_a_triple_and_an_x_wing():
    hardest = {_generated(Tier.HARD, seed).grade.hardest for seed in HARD_SEEDS}
    assert "x_wing" in hardest
    assert hardest & {"naked_triple", "hidden_triple"}


# --- Uniqueness, proved independently of the generator ------------------------


@pytest.mark.parametrize(
    ("tier", "seed"),
    [(Tier.EASY, s) for s in range(5)] + [(Tier.MEDIUM, s) for s in range(3)] + [(Tier.HARD, 5)],
)
def test_every_generated_puzzle_has_exactly_one_solution(tier, seed):
    puzzle = _generated(tier, seed)
    assert count_solutions(puzzle.givens) == 1
    assert unique_solution(puzzle.givens) == puzzle.solution
    # And the grader, from the givens alone, reaches that same solution.
    result = solve(puzzle.givens)
    assert result is not None
    assert result[0] == puzzle.solution


# --- Determinism and no peeking -----------------------------------------------


def test_the_grader_gives_the_same_result_every_time():
    puzzle = _generated(Tier.MEDIUM, seed=1)
    first = grade(puzzle.givens)
    for _ in range(3):
        assert grade(puzzle.givens) == first


# --- Published puzzles: pending -----------------------------------------------

PUBLISHED: list[tuple[str, str, str]] = []
"""Puzzles with a published rating, as ``(givens, expected_hardest, source)``,
ordered from easiest to hardest by the source.

Pending: the puzzles must be copied exactly from a cited source (a single wrong
digit is a different puzzle), and none has been added yet. ``DIFFICULTY.md``
requires two checks on them, both written below and skipped until the list is
filled:

- a puzzle known to need one specific technique grades as that technique's tier;
- the grader ranks the list in the same relative order as the source (by tier:
  exact labels need not agree, but the order must).
"""


@pytest.mark.skipif(not PUBLISHED, reason="no published puzzles added yet")
def test_published_puzzles_grade_as_their_known_technique():
    for givens, expected, source in PUBLISHED:
        g = grade(givens)
        assert g is not None, f"discarded: {source}"
        assert g.tier is TIER_OF[expected], source


@pytest.mark.skipif(not PUBLISHED, reason="no published puzzles added yet")
def test_published_puzzles_keep_their_relative_order():
    # Compared by tier: ranking within a tier is a non-goal of DIFFICULTY.md.
    order = list(Tier)
    ranks = []
    for givens, _, source in PUBLISHED:
        g = grade(givens)
        assert g is not None, f"discarded: {source}"
        ranks.append(order.index(g.tier))
    assert ranks == sorted(ranks)
