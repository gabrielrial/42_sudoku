"""Deleting an account and a move take their locks in the same order.

An input locks its game, then its ``game_moves`` row needs the user (the foreign
key takes ``FOR KEY SHARE``). If the deletion locked the user first and then
reached the game through the cascade, each would hold what the other wants, and
PostgreSQL would kill one of them. Real sessions and a real wait: this cannot be
seen inside one transaction.
"""

import threading
import time
from collections.abc import Iterator
from datetime import date, datetime
from uuid import UUID

import pytest
from sqlalchemy import Engine, delete, func, select, text
from sqlalchemy.orm import Session

from app.clock import UTC
from app.database.models.game_moves import GameMove
from app.database.models.game_sessions import GameSession
from app.database.models.puzzles import Puzzle
from app.database.models.users import User
from app.services.users import delete_user
from tests.api.games import GIVENS, make_puzzle

pytestmark = pytest.mark.db

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


@pytest.fixture
def game(db_engine: Engine) -> Iterator[tuple[int, UUID]]:
    with Session(db_engine) as setup:
        user = User(intra_id=4545, login="lock-order", campus_id=1, campus_name="Berlin")
        setup.add(user)
        puzzle = make_puzzle(setup, date(2000, 1, 3), "easy")
        setup.flush()
        row = GameSession(user_id=user.id, puzzle_id=puzzle.id, state=GIVENS)
        setup.add(row)
        setup.commit()
        user_id, puzzle_id, game_id = user.id, puzzle.id, row.id
    try:
        yield user_id, game_id
    finally:
        with Session(db_engine) as cleanup:
            cleanup.execute(delete(User).where(User.id == user_id))
            cleanup.execute(delete(Puzzle).where(Puzzle.id == puzzle_id))
            cleanup.commit()


def _wait_until_someone_waits_on_a_lock(engine: Engine) -> None:
    query = text(
        "SELECT count(*) FROM pg_stat_activity "
        "WHERE datname = current_database() AND wait_event_type = 'Lock'"
    )
    deadline = time.monotonic() + 5
    with engine.connect() as connection:
        while connection.execute(query).scalar_one() == 0:
            assert time.monotonic() < deadline, "the deletion never reached the game's lock"
            connection.rollback()
            time.sleep(0.01)


def test_a_deletion_waits_for_an_input_in_flight_and_neither_dies(
    db_engine: Engine, game: tuple[int, UUID]
) -> None:
    user_id, game_id = game
    errors: list[Exception] = []

    def delete_the_account() -> None:
        try:
            with Session(db_engine) as session:
                found = session.get(User, user_id)
                assert found is not None
                delete_user(session, found)
        except Exception as exc:
            errors.append(exc)

    deletion = threading.Thread(target=delete_the_account)
    with Session(db_engine) as input_request:
        # What ``play_cell`` does, stopped between its two locks.
        locked = select(GameSession).where(GameSession.id == game_id).with_for_update()
        assert input_request.scalar(locked) is not None

        deletion.start()
        _wait_until_someone_waits_on_a_lock(db_engine)

        input_request.add(GameMove(game_id=game_id, user_id=user_id, kind="clear", played_at=NOW))
        input_request.commit()  # the deadlock, if the order is wrong, comes here

    deletion.join(timeout=10)
    assert not deletion.is_alive()
    assert errors == []
    with Session(db_engine) as observer:
        assert observer.get(User, user_id) is None
        count = select(func.count()).select_from(GameMove).where(GameMove.user_id == user_id)
        assert observer.scalar(count) == 0
