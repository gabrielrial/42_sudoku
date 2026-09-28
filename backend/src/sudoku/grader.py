"""The grader: how hard is a puzzle for a person?

The difficulty of a puzzle is the hardest technique a solver is *forced* to use
to finish it without guessing (``DIFFICULTY.md``). The grader finds out by
solving the puzzle the way a person would:

    while the puzzle is not solved:
        try each technique, easiest first
        on the first one that makes progress, stop and start again from the top
        if none makes progress: give up — the puzzle is discarded

Starting again from the top after every step is what makes the result mean
*required*. A tier-3 technique is only reached when every tier-1 and tier-2
technique is stuck; if the grader simply used whatever applied first, a puzzle
could be labelled Hard because an X-Wing happened to be visible while a hidden
single would have done.

``grade`` takes the givens and nothing else. It cannot consult a stored
solution because it is never given one — a grader that peeks measures nothing.
"""

from dataclasses import dataclass
from enum import Enum

from sudoku import techniques
from sudoku.board import Board


class Tier(Enum):
    """Values match the difficulty strings of the API and the database."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass(frozen=True)
class Step:
    name: str
    tier: Tier
    apply: techniques.Technique


LADDER: tuple[Step, ...] = (
    Step("naked_single", Tier.EASY, techniques.naked_single),
    Step("hidden_single", Tier.EASY, techniques.hidden_single),
    Step("naked_pair", Tier.MEDIUM, techniques.naked_pair),
    Step("hidden_pair", Tier.MEDIUM, techniques.hidden_pair),
    Step("pointing_pair", Tier.MEDIUM, techniques.pointing_pair),
    Step("box_line", Tier.MEDIUM, techniques.box_line),
    Step("naked_triple", Tier.HARD, techniques.naked_triple),
    Step("hidden_triple", Tier.HARD, techniques.hidden_triple),
    Step("x_wing", Tier.HARD, techniques.x_wing),
)
"""Easiest first. This order is the specification, not an implementation detail."""


@dataclass(frozen=True)
class Grade:
    tier: Tier
    hardest: str
    """Name of the hardest technique the solve needed."""
    counts: dict[str, int]
    """How many times each technique fired, every technique listed. Recorded
    for later tuning; not used to decide the tier."""


def solve(givens: str) -> tuple[str, Grade] | None:
    """Solve a puzzle by the ladder alone, from its givens alone.

    Returns the finished grid together with its grade, or ``None`` when the
    ladder cannot finish — the puzzle needs something beyond tier 3, or has no
    solution. Per ``DIFFICULTY.md`` such a puzzle is **discarded, not shipped
    as Hard**.

    The finished grid is what the techniques deduced, never a stored answer;
    tests compare it with the counting solver's result to prove every technique
    is sound.

    Raises ``ValueError`` for a malformed grid, givens that break a rule, or a
    grid that is already full (there is nothing to grade).
    """
    board = Board.from_string(givens)
    if board.is_solved():
        raise ValueError("the grid is already full; there is nothing to grade")

    counts = {step.name: 0 for step in LADDER}
    hardest = -1

    while not board.is_solved():
        if board.is_broken():
            return None
        for position, step in enumerate(LADDER):
            if step.apply(board):
                counts[step.name] += 1
                hardest = max(hardest, position)
                break  # back to the top of the ladder
        else:
            return None  # every technique is stuck

    top = LADDER[hardest]
    return board.to_string(), Grade(tier=top.tier, hardest=top.name, counts=counts)


def grade(givens: str) -> Grade | None:
    """The grade of a puzzle, or ``None`` if it must be discarded. See ``solve``."""
    result = solve(givens)
    return None if result is None else result[1]
