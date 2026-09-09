# Difficulty grading (normative)

The specification the Sudoku engine is built and tested against. Phase 2
implements exactly this.

## Principle

> The difficulty of a puzzle is the **hardest technique a solver is forced to
> use** in order to finish it without guessing.

Two approaches are explicitly rejected:

- **Clue count.** A 26-clue puzzle can be trivial and a 30-clue puzzle brutal.
  What matters is how the given information is arranged, not how much there is.
- **Solver runtime.** A backtracking solver brute-forces any Sudoku in
  milliseconds. It measures nothing a player would recognise.

## Vocabulary

- **Unit** — a row, a column, or a 3×3 box. 27 in total.
- **Candidates** of an empty cell — the digits not already present in its row,
  its column or its box.
- **Technique** — a function that takes the board with its candidate sets,
  applies one named rule, and returns whether it changed anything (placed a
  digit or eliminated a candidate).

The grader works from the givens alone. **It must never consult the stored
solution.** A grader that peeks is measuring nothing.

## The technique ladder

Ordered easiest to hardest. This order is the specification, not an
implementation detail.

### Tier 1

1. **Naked single** — a cell has exactly one candidate. Place it.
2. **Hidden single** — within a unit, a digit is a candidate in exactly one
   cell. Place it there, even if that cell has other candidates.

### Tier 2

3. **Naked pair** — two cells in a unit have identical candidate sets of size 2.
   Those two digits must occupy those two cells: eliminate both digits from
   every other cell in the unit.
4. **Hidden pair** — two digits in a unit are candidates in exactly the same two
   cells. Those cells must hold them: remove all other candidates from those two
   cells.
5. **Pointing pair** — within a box, all candidates for digit `d` lie in a single
   row (or column). `d` must be in that row inside the box: eliminate `d` from
   the rest of that row outside the box.
6. **Box-line reduction** — the mirror of 5. Within a row (or column), all
   candidates for `d` lie inside a single box: eliminate `d` from the rest of
   that box.

### Tier 3

7. **Naked triple** — three cells in a unit whose candidates are drawn from the
   same three digits. Eliminate those digits from the rest of the unit.
8. **Hidden triple** — three digits in a unit that are candidates in exactly the
   same three cells. Remove all other candidates from those cells.
9. **X-Wing** — digit `d` is a candidate in exactly two cells in each of two
   rows, and those cells occupy the same two columns. Eliminate `d` from the
   rest of those two columns. (And the transpose, rows and columns swapped.)

Nothing beyond tier 3 is implemented: no chains, no forcing nets, no
bifurcation. See "The discard rule".

## The grading algorithm

    LADDER = [naked_single, hidden_single,
              naked_pair, hidden_pair, pointing_pair, box_line,
              naked_triple, hidden_triple, x_wing]

    def grade(board):
        used = []
        while not board.solved():
            for technique in LADDER:      # always easiest first
                if technique(board):      # did it change anything?
                    used.append(technique)
                    break                 # restart from the top of the ladder
            else:
                return None               # logic exhausted -> discard
        return tier_of(hardest(used))

The `break` and restart is load-bearing. Because the ladder is retried from the
top after every successful step, a hard technique is only ever reached when
every easier one is stuck. That is what makes "the hardest technique in `used`"
mean *required* rather than merely *applicable*.

This grader is a separate component from the **uniqueness solver**, which is an
ordinary backtracker that counts solutions and stops at 2. Two solvers, two
jobs; do not merge them.

## Tiers

| Tier | Hardest technique required |
|---|---|
| **Easy** | hidden single (tier 1) |
| **Medium** | naked/hidden pair, pointing pair, or box-line reduction (tier 2) |
| **Hard** | naked/hidden triple or X-Wing (tier 3) |

A puzzle solvable by naked singles alone is still Easy; there is no fourth tier
below Easy.

### The discard rule

**A puzzle the ladder cannot finish is discarded, not shipped as Hard.**

Two reasons. Implementing chains and forcing nets correctly is a large amount of
work for a first version, and puzzles requiring them are unpleasant for most
players. If an Expert tier is ever wanted, the ladder is extended and the tier
table gains a row — the design already accommodates that.

## Generation procedure

1. Build a random complete valid grid (randomised backtracking).
2. Walk the cells in random order. Remove one, then run the uniqueness solver.
   If exactly one solution remains, leave the cell removed; otherwise restore it.
3. When no further cell can be removed, run the grader.
4. If the grade matches the requested tier, accept. Otherwise discard the whole
   candidate and start again from step 1.

Step 4 is a retry loop and that is acceptable: generation runs offline, days
ahead of play (`DECISIONS.md` A1), so no user ever waits on it. Easy is expected
to land on most attempts and Hard to take several. If Hard generation proves too
slow, bias the digging order or the starting grid — **do not weaken the grader
to make puzzles easier to find.**

## Metadata to record per puzzle

Stored on the `Puzzle` row, for later tuning and for debugging the grader:

- the assigned tier;
- the hardest technique required;
- how many times each technique fired;
- clue count;
- generator version and seed.

The counts are **not** used for tiering in the MVP. They exist so that ranking
within a tier — a puzzle needing four X-Wings is nastier than one needing a
single one — can be added later without regenerating history.

## Verification requirements

A broken grader fails silently: the application ships three tiers that all feel
the same, and nobody notices for weeks. These tests are therefore not optional.

- Hand-built puzzles known to require exactly one specific technique grade as
  that technique's tier.
- Every generated Easy puzzle is solvable by singles alone — assert that no
  tier-2 or tier-3 technique ever fires on one.
- Published puzzles with known ratings are ranked by this grader in the same
  relative order. Exact label agreement is not required; disagreement about
  which of two puzzles is harder is a failure.
- Every generated puzzle has exactly one solution, verified independently of
  the generator that produced it.
- The grader produces the same tier for the same puzzle on repeated runs, and
  never consults the solution.

## Non-goals

Chains, forcing nets, bifurcation, an Expert tier, difficulty ranking within a
tier, per-user adaptive difficulty. None of these are in scope. Adding one is a
change to this document first.
