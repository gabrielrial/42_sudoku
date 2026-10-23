"""The daily puzzles and, apart from them, their solutions (``DATA_MODEL.md``).

The solution is the one secret in the system (``SECURITY.md``). It lives in its
own table, and ``Puzzle`` deliberately has no relationship to it: loading a
puzzle can never bring its solution along, and reading one takes a query that
names ``PuzzleSolution``. Only the completion check and the generator do.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.conf.alch_conf import Base

DIFFICULTIES = ("easy", "medium", "hard")


class Puzzle(Base):
    __tablename__ = "puzzles"
    __table_args__ = (
        # One puzzle per day per difficulty, as a database guarantee (A1). Its
        # index also serves lookups by date alone: puzzle_date is its first column.
        UniqueConstraint("puzzle_date", "difficulty", name="puzzles_puzzle_date_difficulty_key"),
        CheckConstraint(
            "difficulty IN ('easy', 'medium', 'hard')", name="puzzles_difficulty_check"
        ),
        CheckConstraint("givens ~ '^[0-9]{81}$'", name="puzzles_givens_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    puzzle_date: Mapped[date] = mapped_column(Date)
    """A Europe/Berlin calendar day (D1)."""
    difficulty: Mapped[str] = mapped_column(Text)
    givens: Mapped[str] = mapped_column(CHAR(81))
    clue_count: Mapped[int] = mapped_column(SmallInteger)
    hardest_technique: Mapped[str] = mapped_column(Text)
    technique_counts: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    generator_version: Mapped[str] = mapped_column(Text)
    seed: Mapped[int | None] = mapped_column(BigInteger)
    """Traceability only: puzzles are never regenerated (A1)."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PuzzleSolution(Base):
    __tablename__ = "puzzle_solutions"
    __table_args__ = (
        CheckConstraint("solution ~ '^[1-9]{81}$'", name="puzzle_solutions_solution_check"),
    )

    puzzle_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("puzzles.id", ondelete="CASCADE"), primary_key=True
    )
    solution: Mapped[str] = mapped_column(CHAR(81))
