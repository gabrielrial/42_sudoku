"""Durations stay right whatever time zone a database session uses.

The night summer time ends (24 -> 25 October 2026), 23:30Z is 01:30 CEST and
01:30Z is 02:30 CET: two real hours, one hour apart on the wall clock. In a
Europe/Berlin session PostgreSQL hands both back labelled Europe/Berlin, and
Python subtracts such a pair as wall-clock times. Each test first shows that
its setup really reproduces that, so it cannot pass vacuously.
"""

from collections.abc import Iterator
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from app.clock import UTC
from app.database.conf.alch_conf import make_engine
from app.database.models.game_sessions import GameSession
from app.database.models.puzzles import Puzzle
from app.database.models.users import User
from app.services.games import official_seconds

pytestmark = pytest.mark.db

GIVENS = "000090001084000000092040000007203000600514002000000300000000960000000700001078400"
STARTED = datetime(2026, 10, 24, 23, 30, tzinfo=UTC)
COMPLETED = datetime(2026, 10, 25, 1, 30, tzinfo=UTC)


def test_official_time_is_real_time_in_a_berlin_session(db: Session, user: User) -> None:
    puzzle = Puzzle(
        puzzle_date=date(2026, 10, 24),
        difficulty="hard",
        givens=GIVENS,
        clue_count=26,
        hardest_technique="x",
        technique_counts={},
        generator_version="1",
    )
    db.add(puzzle)
    db.flush()
    game = GameSession(
        user_id=user.id,
        puzzle_id=puzzle.id,
        state=GIVENS,
        started_at=STARTED,
        completed_at=COMPLETED,
    )
    db.add(game)
    db.flush()
    db.execute(text("SET LOCAL timezone = 'Europe/Berlin'"))  # undone with the test
    db.expire_all()

    loaded = db.get(GameSession, game.id)
    assert loaded is not None and loaded.completed_at is not None
    # The setup reproduces the trap: plain subtraction is an hour short here.
    assert loaded.completed_at - loaded.started_at == timedelta(hours=1)

    assert official_seconds(loaded) == 2 * 3600


@pytest.fixture
def berlin_by_default(db_engine: Engine) -> Iterator[str]:
    """The test database made to default to Europe/Berlin, then put back."""
    name = db_engine.url.database
    with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"ALTER DATABASE \"{name}\" SET timezone = 'Europe/Berlin'"))
    try:
        yield str(db_engine.url.render_as_string(hide_password=False))
    finally:
        with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(f'ALTER DATABASE "{name}" RESET timezone'))


def _session_zone(engine: Engine) -> str:
    try:
        with engine.connect() as conn:
            return str(conn.execute(text("SHOW timezone")).scalar_one())
    finally:
        engine.dispose()


def test_the_applications_connections_use_utc_whatever_the_default(berlin_by_default: str) -> None:
    # Control: a connection that does not insist gets the database's default.
    assert _session_zone(create_engine(berlin_by_default)) == "Europe/Berlin"

    assert _session_zone(make_engine(berlin_by_default)) == "UTC"
