"""What the puzzle and game endpoints answer (``API.md``, Puzzles and Games).

Each model lists exactly the fields the API promises, and nothing here has a
field for the solution: it cannot leak through a response by accident.
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictInt

Difficulty = Literal["easy", "medium", "hard"]
TodayStatus = Literal["not_started", "in_progress", "completed", "closed"]


class TodayPuzzle(BaseModel):
    """One difficulty of today, from the caller's side. Never its cells (Q13)."""

    difficulty: Difficulty
    status: TodayStatus
    game_id: uuid.UUID | None
    official_seconds: int | None
    """Completed games only: ``completed_at - started_at`` (D2)."""
    active_seconds: int | None
    """Completed games only: the advisory active time (D10)."""


class Today(BaseModel):
    date: date
    puzzles: list[TodayPuzzle]


class NewGame(BaseModel):
    difficulty: Difficulty


class GameStarted(BaseModel):
    game_id: uuid.UUID
    difficulty: Difficulty
    date: date
    givens: str
    state: str
    started_at: datetime


class GameView(BaseModel):
    """Everything needed to rebuild the board when resuming (``API.md``)."""

    game_id: uuid.UUID
    difficulty: Difficulty
    date: date
    givens: str
    state: str
    status: Literal["in_progress", "completed"]
    """Never "closed": a closed game answers 410 instead."""
    started_at: datetime
    completed_at: datetime | None
    official_seconds: int | None
    active_seconds: int
    submission_count: int


class CellInput(BaseModel):
    """``{"value": 7}``, or ``{"value": null}`` to clear. The key is required.

    ``StrictInt``: ``"7"``, ``7.0`` and ``true`` are refused, not coerced. The
    client is hostile; nothing it sends is interpreted generously.
    """

    value: Annotated[StrictInt, Field(ge=1, le=9)] | None
