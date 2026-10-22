"""The verification requirements of ``DIFFICULTY.md``, one section each.

A broken grader fails silently: three tiers that all feel the same, and nobody
notices for weeks. These tests are how it fails loudly instead.
"""

import random
from dataclasses import dataclass
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


# --- An outside opinion: SudokuWiki's solver --------------------------------------
# A grader checked only against puzzles it graded itself agrees with itself,
# broken or not. These puzzles carry a second opinion: the solve path of Andrew
# Stuart's solver at https://www.sudokuwiki.org/sudoku.htm (version 2.71.2,
# read on 2026-10-22), an implementation independent of this one. Its ladder
# begins like ours: singles; naked and hidden pairs; pointing pairs; box/line
# reduction; naked and hidden triples; then, among its "tough" strategies,
# X-Wing. Everything else it uses is beyond tier 3 here.
#
# ``used`` is what that solve path listed, in SudokuWiki's own words. The grids
# are copied by program from the solver's page (``?bd=`` and its own
# ``makePuzzleString``), never retyped: one wrong digit is another puzzle.
# No published SudokuWiki puzzle stays within tier 3 and needs a triple or an
# X-Wing, so the two Hard references are puzzles from this generator (seeds 5
# and 4), rated by SudokuWiki's solver.

SUDOKUWIKI_TIER = {
    "Naked Singles": Tier.EASY,
    "Hidden Singles": Tier.EASY,
    "Naked Pair": Tier.MEDIUM,
    "Hidden Pair": Tier.MEDIUM,
    "Pointing Pairs": Tier.MEDIUM,
    "Line/Unit Reduction": Tier.MEDIUM,
    "Naked Triple": Tier.HARD,
    "Hidden Triple": Tier.HARD,
    "X-Wing": Tier.HARD,
}
"""SudokuWiki's names for the techniques of our ladder. Any other means beyond tier 3."""

OUR_NAME = {
    "Naked Singles": "naked_single",
    "Hidden Singles": "hidden_single",
    "Naked Pair": "naked_pair",
    "Hidden Pair": "hidden_pair",
    "Pointing Pairs": "pointing_pair",
    "Line/Unit Reduction": "box_line",
    "Naked Triple": "naked_triple",
    "Hidden Triple": "hidden_triple",
    "X-Wing": "x_wing",
}


@dataclass(frozen=True)
class Reference:
    name: str
    """Its name in SudokuWiki's "Pick an example" list, or where else it came from."""
    givens: str
    used: tuple[str, ...]
    """The techniques SudokuWiki's solve path used, in its words."""

    @property
    def tier(self) -> Tier | None:
        """The tier SudokuWiki's solve path implies; ``None``: beyond tier 3, discard."""
        if any(technique not in SUDOKUWIKI_TIER for technique in self.used):
            return None
        return max((SUDOKUWIKI_TIER[t] for t in self.used), key=list(Tier).index)


SUDOKUWIKI = [
    Reference(
        "Easiest Sudoku",
        "300967001040302080020000070070000090000873000500010003004705100905000207800621004",
        ("Naked Singles",),
    ),
    Reference(
        "Gentle",
        "000004028406000005100030600000301000087000140000709000002010003900000507670400000",
        ("Hidden Singles", "Naked Singles"),
    ),
    Reference(
        "Moderate",
        "030007000067100350019000000500000007070203010900000008000000680086002970000700040",
        ("Hidden Singles", "Naked Singles", "Naked Pair", "Hidden Pair"),
    ),
    Reference(
        "Pointing Pairs",
        "000001426000000000020905000701090004800010005300060208000108060000000000438600000",
        ("Naked Singles", "Hidden Singles", "Pointing Pairs"),
    ),
    Reference(
        "Line Box Reductions",
        "000004000200030000060900400040301500006000900013207080081006040000070009000400000",
        ("Naked Singles", "Hidden Singles", "Line/Unit Reduction"),
    ),
    Reference(
        "this generator, Hard, seed 5",
        "000090001084000000092040000007203000600514002000000300000000960000000700001078400",
        ("Naked Singles", "Hidden Singles", "Pointing Pairs", "Naked Triple"),
    ),
    Reference(
        "this generator, Hard, seed 4",
        "009200130200009080000500000020000368500000010004030000900001056600700000005400070",
        (
            "Naked Pair",
            "Hidden Singles",
            "Hidden Pair",
            "Pointing Pairs",
            "X-Wing",
            "Naked Singles",
        ),
    ),
    # Beyond tier 3: SudokuWiki needed a technique our ladder does not have.
    Reference(
        "Tough",
        "018050000060000049900207000700006030000308000030500007000709004450000070000020360",
        (
            "Naked Singles",
            "Hidden Singles",
            "Hidden Pair",
            "Pointing Pairs",
            "Line/Unit Reduction",
            "Unique Rectangle Type 1",
            "Y-Wing",
        ),
    ),
    Reference(
        "Naked Triples",
        "000104300000080000009020004560700000030008050000006038801090700000070000004201000",
        (
            "Hidden Singles",
            "Naked Singles",
            "Naked Pair",
            "Pointing Pairs",
            "Naked Triple",
            "Hidden Pair",
            "Unique Rectangle Type 1",
            "W-Wing",
        ),
    ),
    Reference(
        "Hidden Triple",
        "307060090540000008060100000100700000080201070000005004000009030900000067020050809",
        (
            "Naked Singles",
            "Hidden Singles",
            "Naked Pair",
            "Pointing Pairs",
            "Hidden Triple",
            "Hidden Pair",
            "W-Wing",
        ),
    ),
    Reference(
        "X-Wing x3",
        "000900000705080009020007050840009005000705000000100027010400030500090704000002000",
        (
            "Hidden Singles",
            "Naked Singles",
            "Naked Pair",
            "Pointing Pairs",
            "X-Wing",
            "Bi-value Universal Grave",
        ),
    ),
    Reference(
        "Y-Wing x3",
        "540000800000700002003092060010050090300000007020060040060930700700005000001000056",
        ("Naked Singles", "Hidden Singles", "Naked Pair", "Y-Wing", "W-Wing"),
    ),
    Reference(
        # https://www.sudokuwiki.org/X_Wing_Strategy, "X-Wing Exemplars". The page
        # calls it "otherwise trivial"; the solver's own path disagrees.
        "X-Wing Exemplar 1, x3 (score 74)",
        "000001008700030009020000061080009003001040900900300020240000080600090005100600000",
        ("Hidden Singles", "Naked Singles", "X-Wing", "Chute Remote Pair", "Naked Pair"),
    ),
]
"""Ordered from easiest to hardest by SudokuWiki's tier; beyond tier 3 last."""

_RANK = [*Tier, None]


@pytest.mark.parametrize("ref", SUDOKUWIKI, ids=[r.name for r in SUDOKUWIKI])
def test_each_reference_is_unique(ref: Reference) -> None:
    # A typo would make another puzzle, usually one without a single solution.
    assert count_solutions(ref.givens) == 1


@pytest.mark.parametrize("ref", SUDOKUWIKI, ids=[r.name for r in SUDOKUWIKI])
def test_each_reference_gets_the_tier_sudokuwiki_implies(ref: Reference) -> None:
    # Including None: what SudokuWiki needed a technique beyond tier 3 for is
    # discarded here, never shipped as Hard (DIFFICULTY.md, the discard rule).
    g = grade(ref.givens)

    assert (None if g is None else g.tier) is ref.tier


@pytest.mark.parametrize(
    "ref", [r for r in SUDOKUWIKI if r.tier], ids=[r.name for r in SUDOKUWIKI if r.tier]
)
def test_within_tier_3_we_use_the_same_techniques_as_sudokuwiki(ref: Reference) -> None:
    # Stronger than the tier: the same set of techniques fired, not merely the
    # same hardest one. The ladder order is the same in both solvers.
    g = grade(ref.givens)
    assert g is not None

    assert {name for name, n in g.counts.items() if n} == {OUR_NAME[t] for t in ref.used}


def test_the_references_keep_sudokuwikis_order() -> None:
    # DIFFICULTY.md's requirement as worded: the same relative order, exact
    # labels not required. The test above is stricter; this one is the floor.
    ours = []
    for ref in SUDOKUWIKI:
        g = grade(ref.givens)
        ours.append(_RANK.index(None if g is None else g.tier))

    theirs = [_RANK.index(ref.tier) for ref in SUDOKUWIKI]
    assert theirs == sorted(theirs)  # the list itself is in order
    assert ours == sorted(ours)
