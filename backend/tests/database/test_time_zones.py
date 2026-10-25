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
from sqlalchemy import Connection, Engine, create_engine, text
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


def _database_timezone(conn: Connection, name: str) -> str | None:
    """The database's own ``timezone`` setting, if it has one."""
    settings = conn.execute(
        text(
            "SELECT s.setconfig FROM pg_db_role_setting s"
            " JOIN pg_database d ON d.oid = s.setdatabase"
            " WHERE d.datname = :name AND s.setrole = 0"
        ),
        {"name": name},
    ).scalar_one_or_none()
    for setting in settings or []:
        key, _, value = setting.partition("=")
        if key.lower() == "timezone":
            return value
    return None


@pytest.fixture(params=["alter database", "PGTZ"])
def berlin_by_default(
    request: pytest.FixtureRequest, db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[str]:
    """A URL whose connections default to Europe/Berlin, by either way of doing
    it from outside the code; whatever was there before is put back."""
    url = db_engine.url.render_as_string(hide_password=False)
    if request.param == "PGTZ":
        monkeypatch.setenv("PGTZ", "Europe/Berlin")  # libpq reads it on every connect
        yield url
        return
    name = db_engine.url.database
    with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        before = _database_timezone(conn, str(name))
        conn.execute(text(f"ALTER DATABASE \"{name}\" SET timezone = 'Europe/Berlin'"))
    try:
        yield url
    finally:
        with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            if before is None:
                conn.execute(text(f'ALTER DATABASE "{name}" RESET timezone'))
            else:
                conn.execute(
                    text(f'ALTER DATABASE "{name}" SET timezone = :zone'), {"zone": before}
                )


def _session_zone(engine: Engine) -> str:
    try:
        with engine.connect() as conn:
            return str(conn.execute(text("SHOW timezone")).scalar_one())
    finally:
        engine.dispose()


def test_the_applications_connections_use_utc_whatever_the_default(berlin_by_default: str) -> None:
    # Control: a connection that does not insist gets the default from outside.
    assert _session_zone(create_engine(berlin_by_default)) == "Europe/Berlin"

    assert _session_zone(make_engine(berlin_by_default)) == "UTC"


def test_utc_survives_the_pools_rollback(berlin_by_default: str) -> None:
    # A connection back from the pool has been rolled back: the zone must not
    # have been set inside a transaction that rollback undoes.
    engine = make_engine(berlin_by_default, pool_size=1, max_overflow=0)
    try:
        with engine.connect() as conn:
            conn.rollback()
        with engine.connect() as conn:
            assert conn.execute(text("SHOW timezone")).scalar_one() == "UTC"
    finally:
        engine.dispose()
