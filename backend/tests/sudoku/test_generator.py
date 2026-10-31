import random

import pytest

from sudoku.board import has_duplicate, parse_grid
from sudoku.generator import (
    EASY_CLUES,
    GENERATOR_VERSION,
    HARD_CLUES,
    MEDIUM_CLUES,
    GenerationError,
    dig,
    generate,
    refill,
)
from sudoku.grader import Tier, grade
from sudoku.solver import count_solutions, random_full_grid


def test_digging_leaves_a_minimal_puzzle_with_one_solution():
    rng = random.Random(3)
    solution = random_full_grid(rng)
    givens = dig(solution, rng)
    assert count_solutions(givens) == 1
    assert all(g in ("0", s) for g, s in zip(givens, solution, strict=True))
    # Minimal: every remaining given is needed for uniqueness.
    for cell, ch in enumerate(givens):
        if ch != "0":
            fewer = givens[:cell] + "0" + givens[cell + 1 :]
            assert count_solutions(fewer) == 2, f"given at {cell} was removable"


def test_digging_can_stop_at_a_number_of_givens():
    rng = random.Random(3)
    solution = random_full_grid(rng)

    givens = dig(solution, rng, keep=37)

    assert sum(ch != "0" for ch in givens) == 37
    assert count_solutions(givens) == 1


@pytest.mark.parametrize("seed", range(12))
def test_an_easy_puzzle_starts_with_32_to_42_givens(seed: int) -> None:
    # DIFFICULTY.md: a minimal Easy is a long, sparse grid; beginners need more.
    puzzle = generate(Tier.EASY, seed=seed)

    assert puzzle.clue_count in EASY_CLUES
    assert puzzle.grade.tier is Tier.EASY
    assert count_solutions(puzzle.givens) == 1


def test_the_easy_range_is_32_to_42_inclusive():
    assert (min(EASY_CLUES), max(EASY_CLUES)) == (32, 42)


def test_easy_givens_spread_over_the_range():
    # Drawn per puzzle, not one fixed count: a week of Easy varies.
    counts = {generate(Tier.EASY, seed=seed).clue_count for seed in range(30)}
    assert len(counts) >= 5


@pytest.mark.parametrize("seed", range(8))
def test_a_medium_puzzle_starts_with_32_to_36_givens_and_is_still_medium(seed: int) -> None:
    # DIFFICULTY.md: more to start from, the same tier-2 technique required.
    puzzle = generate(Tier.MEDIUM, seed=seed)

    assert puzzle.clue_count in MEDIUM_CLUES
    assert puzzle.grade.tier is Tier.MEDIUM
    assert count_solutions(puzzle.givens) == 1
    assert all(g in ("0", s) for g, s in zip(puzzle.givens, puzzle.solution, strict=True))


def test_the_medium_range_is_32_to_36_inclusive():
    assert (min(MEDIUM_CLUES), max(MEDIUM_CLUES)) == (32, 36)


def test_medium_givens_spread_over_the_range():
    counts = {generate(Tier.MEDIUM, seed=seed).clue_count for seed in range(15)}
    assert len(counts) >= 3


def test_refilling_takes_back_every_clue_that_would_make_it_easier():
    # Asked for far more givens than a Medium can have: it stops short, still Medium.
    rng = random.Random(0)
    while True:
        solution = random_full_grid(rng)
        minimal = dig(solution, rng)
        result = grade(minimal)
        if result is not None and result.tier is Tier.MEDIUM:
            break

    filled = refill(minimal, solution, rng, Tier.MEDIUM, keep=60)

    result = grade(filled)
    assert result is not None and result.tier is Tier.MEDIUM
    assert sum(ch != "0" for ch in minimal) < sum(ch != "0" for ch in filled) < 60
    assert all(g in ("0", s) for g, s in zip(filled, solution, strict=True))


# Seeds that find a Hard in few attempts: a Hard takes about 14 s on average.
QUICK_HARD_SEEDS = (1006, 1016, 1018)


@pytest.mark.parametrize("seed", QUICK_HARD_SEEDS)
def test_a_hard_puzzle_starts_with_30_to_38_givens_and_is_still_hard(seed: int) -> None:
    # DIFFICULTY.md: more to start from, the same tier-3 technique required.
    puzzle = generate(Tier.HARD, seed=seed)

    assert puzzle.clue_count in HARD_CLUES
    assert puzzle.grade.tier is Tier.HARD
    assert count_solutions(puzzle.givens) == 1
    assert all(g in ("0", s) for g, s in zip(puzzle.givens, puzzle.solution, strict=True))


def test_the_hard_range_is_30_to_38_inclusive():
    assert (min(HARD_CLUES), max(HARD_CLUES)) == (30, 38)


def test_a_seed_reproduces_its_puzzle():
    first = generate(Tier.EASY, seed=11)
    again = generate(Tier.EASY, seed=11)
    assert first == again
    assert generate(Tier.EASY, seed=12).givens != first.givens


def test_the_puzzle_records_its_metadata():
    puzzle = generate(Tier.MEDIUM, seed=0)
    assert puzzle.seed == 0
    assert puzzle.generator_version == GENERATOR_VERSION
    assert puzzle.attempts >= 1
    assert puzzle.clue_count == sum(ch != "0" for ch in puzzle.givens)
    assert puzzle.grade.tier is Tier.MEDIUM
    assert not has_duplicate(parse_grid(puzzle.solution))
    assert "0" not in puzzle.solution


def test_running_out_of_attempts_is_an_error():
    # Hard takes on the order of a hundred attempts; one is (almost) never enough.
    seed = next(s for s in range(100) if _first_attempt_is_not_hard(s))
    with pytest.raises(GenerationError):
        generate(Tier.HARD, seed=seed, max_attempts=1)


def _first_attempt_is_not_hard(seed: int) -> bool:
    try:
        generate(Tier.HARD, seed=seed, max_attempts=1)
    except GenerationError:
        return True
    return False
