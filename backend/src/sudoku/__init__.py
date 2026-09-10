"""Pure Sudoku logic: boards, solving, generation, difficulty grading.

This package is a library. It must not import from ``app`` — no FastAPI, no
SQLAlchemy, no configuration, no I/O. It takes plain data and returns plain
data, so it can be tested with no database and no web server, and so that a
change to the web layer can never change how a puzzle is graded.

``tests/sudoku/test_import_boundary.py`` enforces this.

Built in Phase 2, to the specification in docs/DIFFICULTY.md.
"""
