"""The Sudoku engine must not depend on the web application.

Not a style preference: the moment ``sudoku`` imports ``app``, grading a puzzle
needs configuration and a database, and the fast offline test suite that Phase 2
depends on stops being possible. This test makes that regression fail loudly
instead of being discovered weeks later.
"""

import ast
import pathlib

SUDOKU_SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "sudoku"
FORBIDDEN_ROOTS = {"app", "fastapi", "sqlalchemy", "alembic", "pydantic_settings"}


def _imported_roots(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_sudoku_package_imports_nothing_from_the_application():
    offenders: list[str] = []
    for path in sorted(SUDOKU_SRC.rglob("*.py")):
        forbidden = _imported_roots(path) & FORBIDDEN_ROOTS
        if forbidden:
            rel = path.relative_to(SUDOKU_SRC.parent.parent)
            offenders.append(f"{rel} imports {', '.join(sorted(forbidden))}")

    assert not offenders, (
        "The sudoku package must stay a pure library (see its docstring):\n  "
        + "\n  ".join(offenders)
    )
