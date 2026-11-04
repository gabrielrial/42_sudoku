"""Keeping the record of moves to its retention period (D31)."""

from datetime import datetime, timedelta
from typing import cast

from sqlalchemy import CursorResult, delete
from sqlalchemy.orm import Session

from app.database.models.game_moves import GameMove


def purge_old_moves(db: Session, now: datetime, days: int) -> int:
    """Delete the moves older than ``days``. Returns how many went."""
    statement = delete(GameMove).where(GameMove.played_at < now - timedelta(days=days))
    result = cast(CursorResult[tuple[()]], db.execute(statement))
    db.commit()
    return result.rowcount
