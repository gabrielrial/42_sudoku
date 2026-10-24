from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import clock
from app.api.dependencies import get_current_user
from app.config import Settings, get_settings
from app.database.conf.dependencies import get_db
from app.database.models.users import User
from app.database.schema.games import GameStarted, GameView, NewGame
from app.services.game_status import Thresholds
from app.services.games import official_seconds, owned_game, start_game

router = APIRouter(prefix="/games", tags=["games"])


@router.post("", response_model=GameStarted, status_code=status.HTTP_201_CREATED)
def create_game(
    body: NewGame,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> GameStarted:
    """Start today's game of a difficulty. The only moment a grid becomes
    visible, and the moment its clock starts (D2, Q13)."""
    game, puzzle = start_game(db, user, body.difficulty, clock.now())
    return GameStarted(
        game_id=game.id,
        difficulty=body.difficulty,
        date=puzzle.puzzle_date,
        givens=puzzle.givens,
        state=game.state,
        started_at=game.started_at,
    )


@router.get("/{game_id}", response_model=GameView)
def read_game(
    game_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GameView:
    """Resuming: the board as the server holds it. Reading is not activity: it
    neither moves ``last_activity_at`` nor keeps a past-day game alive."""
    owned = owned_game(db, user, game_id, clock.now(), Thresholds.from_settings(settings))
    game, puzzle = owned.game, owned.puzzle
    return GameView(
        game_id=game.id,
        difficulty=puzzle.difficulty,
        date=puzzle.puzzle_date,
        givens=puzzle.givens,
        state=game.state,
        status=owned.status.value,
        started_at=game.started_at,
        completed_at=game.completed_at,
        official_seconds=official_seconds(game),
        active_seconds=game.active_seconds,
        submission_count=game.submission_count,
    )
