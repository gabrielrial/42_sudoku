from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import clock
from app.api.dependencies import get_current_user
from app.config import Settings, get_settings
from app.database.conf.dependencies import get_db
from app.database.models.users import User
from app.database.schema.games import ContinuingGame, Today, TodayPuzzle
from app.services.game_status import Thresholds
from app.services.games import todays_puzzles

router = APIRouter(prefix="/puzzles", tags=["puzzles"])


@router.get("/today", response_model=Today)
def today(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Today:
    """The home page's data: today's difficulties and the caller's status on
    each, and any game of an earlier day still open. Never a cell (Q13)."""
    day, entries, continuing = todays_puzzles(
        db, user, clock.now(), Thresholds.from_settings(settings)
    )
    return Today(
        date=day,
        puzzles=[
            TodayPuzzle(
                difficulty=e.difficulty,
                status=e.status,
                game_id=e.game_id,
                official_seconds=e.official_seconds,
                active_seconds=e.active_seconds,
            )
            for e in entries
        ],
        continuing=[
            ContinuingGame(game_id=c.game_id, difficulty=c.difficulty, date=c.date)
            for c in continuing
        ],
    )
