"""What a player did in a game, one row per action, to diagnose failures (D31).

The grid itself stays a snapshot on ``game_sessions`` (D14), and nothing reads
this table to play: it is written alongside, and kept for ``MOVE_LOG_DAYS``. No
endpoint serves it. A digit is recorded as typed, never compared with the
solution: only a ``check`` carries a right-or-wrong, the one the player was told.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    UUID,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.conf.alch_conf import Base


class GameMove(Base):
    __tablename__ = "game_moves"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('input', 'notes', 'clear', 'check')", name="game_moves_kind_check"
        ),
        CheckConstraint(
            "(kind = 'input') = "
            "(cell IS NOT NULL AND previous_value IS NOT NULL AND value IS NOT NULL)",
            name="game_moves_input_check",
        ),
        CheckConstraint(
            "(kind = 'notes') = "
            "(cell IS NOT NULL AND previous_notes IS NOT NULL AND notes IS NOT NULL)",
            name="game_moves_notes_check",
        ),
        CheckConstraint("(kind = 'check') = (correct IS NOT NULL)", name="game_moves_check_check"),
        CheckConstraint("previous_notes BETWEEN 0 AND 511", name="game_moves_previous_notes_check"),
        CheckConstraint("notes BETWEEN 0 AND 511", name="game_moves_notes_range_check"),
        CheckConstraint("cell BETWEEN 0 AND 80", name="game_moves_cell_check"),
        CheckConstraint("previous_value BETWEEN 0 AND 9", name="game_moves_previous_value_check"),
        CheckConstraint("value BETWEEN 0 AND 9", name="game_moves_value_check"),
        # "What did this user do", and "what happened in this game", in order.
        Index("ix_game_moves_user_id_played_at", "user_id", "played_at"),
        Index("ix_game_moves_game_id_played_at", "game_id", "played_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("game_sessions.id", ondelete="CASCADE")
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    """Also reachable through the game; here so that it can be indexed."""
    kind: Mapped[str] = mapped_column(Text)
    cell: Mapped[int | None] = mapped_column(SmallInteger)
    previous_value: Mapped[int | None] = mapped_column(SmallInteger)
    """What the cell held, 0 for empty, as in the grid."""
    value: Mapped[int | None] = mapped_column(SmallInteger)
    previous_notes: Mapped[int | None] = mapped_column(SmallInteger)
    """A ``notes`` move: the cell's notes before, as a bitmask (D33)."""
    notes: Mapped[int | None] = mapped_column(SmallInteger)
    """A ``notes`` move: the cell's notes after. The notes a placed digit removes
    from its peers are not rows of their own: replaying the input redoes it."""
    correct: Mapped[bool | None] = mapped_column(Boolean)
    played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
