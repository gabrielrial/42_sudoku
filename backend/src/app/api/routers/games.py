from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import clock
from app.api.dependencies import get_current_user
from app.database.conf.dependencies import get_db
from app.database.models.users import User
from app.database.schema.games import GameStarted, NewGame
from app.services.games import start_game

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
