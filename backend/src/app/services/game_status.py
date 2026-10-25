"""Where a game stands, computed on read (``GAME_RULES.md`` §3, ``DECISIONS.md`` Q1).

Nothing here touches the database or the clock: the caller passes the instant
and the thresholds, so every rule below is tested by stating a time.

A game is **completed** once its grid was verified. Otherwise, a game whose
puzzle belongs to an earlier Berlin day is **closed** when either

- it has had no contact for longer than the inactivity threshold, or
- the hard deadline has passed: the grace period after the midnight that ended
  its day, whatever the activity.

Anything else is **in progress**, including any game of today's puzzle, however
idle: within its own day a game never closes.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from app.clock import rollover_deadline, today
from app.config import Settings


class Status(StrEnum):
    """Values are the ``status`` strings of the API."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CLOSED = "closed"


@dataclass(frozen=True)
class Thresholds:
    inactivity: timedelta
    grace: timedelta

    @classmethod
    def from_settings(cls, settings: Settings) -> "Thresholds":
        return cls(
            inactivity=timedelta(minutes=settings.game_inactivity_minutes),
            grace=timedelta(minutes=settings.game_rollover_grace_minutes),
        )


def session_status(
    *,
    puzzle_date: date,
    completed_at: datetime | None,
    last_activity_at: datetime,
    now: datetime,
    thresholds: Thresholds,
) -> Status:
    if completed_at is not None:
        return Status.COMPLETED
    if puzzle_date >= today(now):
        return Status.IN_PROGRESS
    idle = now - last_activity_at > thresholds.inactivity
    past_deadline = now >= rollover_deadline(puzzle_date, thresholds.grace)
    return Status.CLOSED if idle or past_deadline else Status.IN_PROGRESS
