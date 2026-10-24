"""Games: listing today's puzzles and starting one (``GAME_RULES.md`` §2, ``API.md``).

Seeing a puzzle is starting its clock (Q13). The listing of today's puzzles
therefore never carries a cell, and the only way to a grid is to create a game,
which sets ``started_at`` and can never be undone (D3).

A game can only be created for **today's** puzzle, today being the Berlin day
(D1, D6). The request names a difficulty, never a date: there is no way to ask
for another day's puzzle at all.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.clock import today
from app.database.models.game_sessions import GameSession
from app.database.models.puzzles import DIFFICULTIES, Puzzle, PuzzleSolution
from app.database.models.users import User
from app.errors import APIError
from app.services.game_status import Status, Thresholds, session_status


@dataclass(frozen=True)
class TodayEntry:
    difficulty: str
    status: str
    game_id: uuid.UUID | None
    official_seconds: int | None
    active_seconds: int | None


def official_seconds(game: GameSession) -> int | None:
    """``completed_at - started_at`` in whole seconds (D2); ``None`` until completed."""
    if game.completed_at is None:
        return None
    return int((game.completed_at - game.started_at).total_seconds())


def todays_puzzles(
    db: Session, user: User, now: datetime, thresholds: Thresholds
) -> tuple[date, list[TodayEntry]]:
    """Today's difficulties and where the caller stands on each. A difficulty
    with no puzzle generated for today is left out (``API.md``)."""
    day = today(now)
    rows = db.execute(select(Puzzle.id, Puzzle.difficulty).where(Puzzle.puzzle_date == day)).all()
    puzzle_ids = {difficulty: puzzle_id for puzzle_id, difficulty in rows}
    games = {
        game.puzzle_id: game
        for game in db.scalars(
            select(GameSession).where(
                GameSession.user_id == user.id,
                GameSession.puzzle_id.in_(puzzle_ids.values()),
            )
        )
    }
    entries = []
    for difficulty in DIFFICULTIES:
        if difficulty not in puzzle_ids:
            continue
        game = games.get(puzzle_ids[difficulty])
        if game is None:
            entries.append(TodayEntry(difficulty, "not_started", None, None, None))
            continue
        game_status = session_status(
            puzzle_date=day,
            completed_at=game.completed_at,
            last_activity_at=game.last_activity_at,
            now=now,
            thresholds=thresholds,
        )
        completed = game_status is Status.COMPLETED
        entries.append(
            TodayEntry(
                difficulty,
                game_status.value,
                game.id,
                official_seconds(game),
                game.active_seconds if completed else None,
            )
        )
    return day, entries


def start_game(
    db: Session, user: User, difficulty: str, now: datetime
) -> tuple[GameSession, Puzzle]:
    """Create the caller's game of today's puzzle of ``difficulty``.

    ``503 puzzle_unavailable`` when today has no such puzzle (Q11: no
    generation on demand). ``409 game_already_exists``, with its ``game_id``,
    when the caller already has one — also when two requests race to create it:
    the unique constraint decides, and the loser is answered like a repeat.
    """
    puzzle = db.scalar(
        select(Puzzle).where(Puzzle.puzzle_date == today(now), Puzzle.difficulty == difficulty)
    )
    if puzzle is None:
        raise APIError(
            "puzzle_unavailable",
            "There is no puzzle of that difficulty today.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    existing = _game_of(db, user, puzzle)
    if existing is not None:
        raise _already_exists(existing)

    game = GameSession(
        user_id=user.id,
        puzzle_id=puzzle.id,
        state=puzzle.givens,
        started_at=now,  # the official clock starts here (D2)
        last_activity_at=now,
    )
    try:
        db.add(game)
        db.commit()
    except IntegrityError:
        db.rollback()
        winner = _game_of(db, user, puzzle)
        if winner is None:  # not the race: some other constraint, a real error
            raise
        raise _already_exists(winner) from None
    return game, puzzle


def _game_of(db: Session, user: User, puzzle: Puzzle) -> GameSession | None:
    return db.scalar(
        select(GameSession).where(
            GameSession.user_id == user.id, GameSession.puzzle_id == puzzle.id
        )
    )


def _already_exists(game: GameSession) -> APIError:
    return APIError(
        "game_already_exists",
        "You have already started this puzzle.",
        status.HTTP_409_CONFLICT,
        extra={"game_id": str(game.id)},
    )


# --- an existing game: the caller's, or nobody's ---------------------------------------


@dataclass(frozen=True)
class OwnedGame:
    game: GameSession
    puzzle: Puzzle
    status: Status


def owned_game(
    db: Session,
    user: User,
    game_id: str,
    now: datetime,
    thresholds: Thresholds,
    *,
    for_update: bool = False,
) -> OwnedGame:
    """The caller's game ``game_id``, with its puzzle and status.

    ``404 game_not_found`` when there is no such game *or* it is someone else's:
    the two answers are identical, so an id never confirms that a game exists
    (``API.md``, Authorisation). ``410 game_closed`` when the rollover closed it.
    ``for_update`` locks the row until the caller's commit, so two requests on
    one game take turns instead of overwriting each other.
    """
    try:
        key = uuid.UUID(game_id)
    except ValueError:
        raise _not_found() from None
    query = (
        select(GameSession, Puzzle)
        .join(Puzzle, Puzzle.id == GameSession.puzzle_id)
        .where(GameSession.id == key, GameSession.user_id == user.id)
    )
    if for_update:
        query = query.with_for_update(of=GameSession)
    row = db.execute(query).one_or_none()
    if row is None:
        raise _not_found()
    game, puzzle = row
    game_status = session_status(
        puzzle_date=puzzle.puzzle_date,
        completed_at=game.completed_at,
        last_activity_at=game.last_activity_at,
        now=now,
        thresholds=thresholds,
    )
    if game_status is Status.CLOSED:
        raise APIError(
            "game_closed",
            "This game was closed when its day ended.",
            status.HTTP_410_GONE,
        )
    return OwnedGame(game, puzzle, game_status)


def _not_found() -> APIError:
    return APIError("game_not_found", "No such game.", status.HTTP_404_NOT_FOUND)


# --- playing: inputs and heartbeats -------------------------------------------------------
# Both prove presence, and only the server's clock measures it (API.md,
# heartbeat). Neither looks at the solution: whether a digit is right is not
# something this path knows, so it cannot leak it (SECURITY.md, the oracle).


def play_cell(
    db: Session, owned: OwnedGame, index: int, value: int | None, now: datetime, gap: timedelta
) -> None:
    """Write ``value`` (1-9, or ``None`` to clear) into cell ``index``.

    Legality only (GAME_RULES.md §3): the game is open and the cell is not a
    given. A wrong digit is an ordinary input, stored like any other.
    """
    game = _open(owned)
    if owned.puzzle.givens[index] != "0":
        raise APIError(
            "cell_is_given", "That cell is part of the puzzle.", status.HTTP_409_CONFLICT
        )
    digit = "0" if value is None else str(value)
    game.state = game.state[:index] + digit + game.state[index + 1 :]
    _touch(game, now, gap)
    db.commit()


def heartbeat(db: Session, owned: OwnedGame, now: datetime, gap: timedelta) -> None:
    """The player is here. Nothing else changes."""
    _touch(_open(owned), now, gap)
    db.commit()


def _open(owned: OwnedGame) -> GameSession:
    """The game, if it can still be played. (Closed games never get here:
    ``owned_game`` answered 410 already.)"""
    if owned.status is Status.COMPLETED:
        raise APIError(
            "game_completed", "This game is already completed.", status.HTTP_409_CONFLICT
        )
    return owned.game


def _touch(game: GameSession, now: datetime, gap: timedelta) -> None:
    """Record a contact. The time since the previous one counts as active time
    when it is short enough to be play rather than absence (D10)."""
    delta = now - game.last_activity_at
    if timedelta(0) < delta <= gap:
        game.active_seconds += round(delta.total_seconds())
    game.last_activity_at = max(now, game.last_activity_at)


# --- completion: the one place the solution is read -------------------------------------


@dataclass(frozen=True)
class Completion:
    correct: bool
    submission_count: int
    official_seconds: int | None
    active_seconds: int | None


def complete(db: Session, owned: OwnedGame, now: datetime, gap: timedelta) -> Completion:
    """Check the grid the server holds against the solution (D13).

    The answer is one boolean, never which cells are wrong (SECURITY.md). Every
    full-grid submission is counted (D22); a grid with empty cells is not a
    submission at all. Idempotent once correct: the stored result is returned
    and ``completed_at`` never moves.
    """
    game = owned.game
    if owned.status is Status.COMPLETED:
        return _result(game, correct=True)
    if "0" in game.state:
        raise APIError(
            "grid_incomplete", "Fill every cell before submitting.", status.HTTP_409_CONFLICT
        )
    solution = db.get(PuzzleSolution, owned.puzzle.id)
    if solution is None:  # a puzzle is never stored without one (services/puzzles.py)
        raise RuntimeError(f"puzzle {owned.puzzle.id} has no solution")

    _touch(game, now, gap)
    game.submission_count += 1
    # Constant time: an ordinary comparison stops at the first difference, and
    # how long it took would hint at how many leading cells are right.
    correct = secrets.compare_digest(game.state.encode(), solution.solution.encode())
    if correct:
        game.completed_at = now  # only ever written after this check (D2)
    db.commit()
    return _result(game, correct=correct)


def _result(game: GameSession, *, correct: bool) -> Completion:
    if not correct:
        return Completion(False, game.submission_count, None, None)
    return Completion(True, game.submission_count, official_seconds(game), game.active_seconds)
