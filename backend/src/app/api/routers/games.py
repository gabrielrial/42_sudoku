from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, status
from sqlalchemy.orm import Session

from app import clock
from app.api.dependencies import get_current_user
from app.api.rate_limits import enforce
from app.config import Settings, get_settings
from app.database.conf.dependencies import get_db
from app.database.models.users import User
from app.database.schema.games import (
    CellInput,
    CompletionResult,
    GameStarted,
    GameView,
    NewGame,
)
from app.services.game_status import Status, Thresholds
from app.services.games import (
    complete,
    heartbeat,
    official_seconds,
    owned_game,
    play_cell,
    start_game,
)

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


@router.put("/{game_id}/cells/{index}", status_code=status.HTTP_204_NO_CONTENT)
def put_cell(
    game_id: str,
    index: Annotated[int, Path(ge=0, le=80)],
    body: CellInput,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """One input. Legality only: never whether the digit is right."""
    now = clock.now()
    # The row stays locked until play_cell commits: two inputs on one game
    # take turns, so neither overwrites the other's cell.
    owned = owned_game(db, user, game_id, now, Thresholds.from_settings(settings), for_update=True)
    # After ownership: nobody can spend another player's inputs by guessing an id.
    enforce(request.app.state.input_limiter, str(owned.game.id), "Too many inputs. Slow down.")
    play_cell(
        db, owned, index, body.value, now, timedelta(seconds=settings.game_active_gap_seconds)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{game_id}/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
def post_heartbeat(
    game_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """The player is here (every 60 s while a game is open, GAME_RULES.md §3)."""
    now = clock.now()
    owned = owned_game(db, user, game_id, now, Thresholds.from_settings(settings), for_update=True)
    enforce(request.app.state.heartbeat_limiter, str(owned.game.id), "Too many heartbeats.")
    heartbeat(db, owned, now, timedelta(seconds=settings.game_active_gap_seconds))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{game_id}/complete", response_model=CompletionResult, response_model_exclude_none=True
)
def post_complete(
    game_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CompletionResult:
    """Check the grid the server holds. No request body: a grid sent with the
    request could disagree with the stored one (LESSONS.md D), and is ignored."""
    now = clock.now()
    owned = owned_game(db, user, game_id, now, Thresholds.from_settings(settings), for_update=True)
    # A completed game answers its stored result without spending a token: there
    # is nothing left to guess. Otherwise this is the brute-force path (D5).
    if owned.status is not Status.COMPLETED:
        enforce(request.app.state.completion_limiter, str(owned.game.id), "Too many submissions.")
    result = complete(db, owned, now, timedelta(seconds=settings.game_active_gap_seconds))
    return CompletionResult(
        correct=result.correct,
        submission_count=result.submission_count,
        official_seconds=result.official_seconds,
        active_seconds=result.active_seconds,
    )
