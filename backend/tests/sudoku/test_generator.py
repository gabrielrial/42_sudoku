import random

import pytest

from sudoku.board import has_duplicate, parse_grid
from sudoku.generator import GENERATOR_VERSION, GenerationError, dig, generate
from sudoku.grader import Tier
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
