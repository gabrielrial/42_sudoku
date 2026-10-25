"""One game: a user playing one puzzle, from start to wherever it ended (``DATA_MODEL.md``).

The status — in progress, completed, closed by the rollover — is not stored. It
is computed on read from these columns and the puzzle's date
(``app/services/game_status.py``), so it can never drift. ``closed_at`` exists
for Phase 8's statistics and stays empty in the MVP (D22).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    UUID,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.conf.alch_conf import Base


class GameSession(Base):
    __tablename__ = "game_sessions"
    __table_args__ = (
        # One game per user per puzzle, forever: no restarts (D3). Its index
        # also serves "this user's games": user_id is its first column.
        UniqueConstraint("user_id", "puzzle_id", name="game_sessions_user_id_puzzle_id_key"),
        CheckConstraint("state ~ '^[0-9]{81}$'", name="game_sessions_state_check"),
        # The daily leaderboards (Phase 8) read completed games of one puzzle.
        Index(
            "ix_game_sessions_puzzle_id_completed_at",
            "puzzle_id",
            "completed_at",
            postgresql_where=text("completed_at IS NOT NULL"),
        ),
    )
    # Read the database's defaults back on insert (RETURNING): sessions keep
    # their objects after commit (expire_on_commit=False), and an endpoint
    # answers from the row it just created.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    """In URLs. Random, so ids reveal neither order nor how many games exist."""
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    puzzle_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("puzzles.id", ondelete="RESTRICT")
    )
    """Bound for good (D6, D7): never updated, and the puzzle cannot be deleted under it."""
    state: Mapped[str] = mapped_column(CHAR(81))
    """The grid as it stands: the givens plus every input, '0' for an empty cell."""
    state_version: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))
    """Format version, so pencil marks can arrive later as an upgrade (Q5)."""
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    active_seconds: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    submission_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
