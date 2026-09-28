"""Command line: ``python -m sudoku generate --difficulty hard [--seed N]``.

A developer tool — the Phase 2 exit check — and the only module in the package
that does any I/O (it prints). Nothing in the library imports it.

It prints the solution too. That is fine here: this runs on a developer's
machine, not on the server, and the solution rule in ``SECURITY.md`` is about
what reaches players.
"""

import argparse
import json
import secrets
import sys
import time
from collections.abc import Sequence

from sudoku.generator import GenerationError, generate
from sudoku.grader import Tier
from sudoku.solver import count_solutions


def _pretty(grid: str) -> str:
    lines = []
    for r in range(9):
        if r in (3, 6):
            lines.append("------+-------+------")
        row = grid[r * 9 : r * 9 + 9].replace("0", ".")
        lines.append(" | ".join(" ".join(row[i : i + 3]) for i in (0, 3, 6)))
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sudoku")
    commands = parser.add_subparsers(dest="command", required=True)
    gen = commands.add_parser("generate", help="generate one graded puzzle")
    gen.add_argument("--difficulty", choices=[t.value for t in Tier], required=True)
    gen.add_argument("--seed", type=int, help="reproduce a puzzle (default: random)")
    gen.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    seed = args.seed if args.seed is not None else secrets.randbelow(2**32)
    started = time.perf_counter()
    try:
        puzzle = generate(Tier(args.difficulty), seed)
    except GenerationError as exc:
        print(exc, file=sys.stderr)
        return 1
    elapsed = time.perf_counter() - started

    # Re-proved here, independently of the generator: exactly one solution.
    solutions = count_solutions(puzzle.givens)

    if args.json:
        print(
            json.dumps(
                {
                    "difficulty": puzzle.grade.tier.value,
                    "givens": puzzle.givens,
                    "solution": puzzle.solution,
                    "hardest_technique": puzzle.grade.hardest,
                    "technique_counts": puzzle.grade.counts,
                    "clue_count": puzzle.clue_count,
                    "seed": puzzle.seed,
                    "generator_version": puzzle.generator_version,
                    "attempts": puzzle.attempts,
                    "unique": solutions == 1,
                },
                indent=2,
            )
        )
    else:
        fired = ", ".join(f"{k} x{v}" for k, v in puzzle.grade.counts.items() if v)
        print(_pretty(puzzle.givens))
        print()
        print(f"difficulty   {puzzle.grade.tier.value}")
        print(f"hardest      {puzzle.grade.hardest}")
        print(f"techniques   {fired}")
        print(f"clues        {puzzle.clue_count}")
        print(f"unique       {'yes' if solutions == 1 else 'NO'}")
        print(f"seed         {puzzle.seed}  (generator v{puzzle.generator_version})")
        print(f"attempts     {puzzle.attempts} in {elapsed:.1f}s")
        print(f"givens       {puzzle.givens}")
    return 0 if solutions == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
