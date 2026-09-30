import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-only-not-a-real-secret")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://sudoku:sudoku@localhost:5442/sudoku_test"
)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


# --- database ----------------------------------------------------------------
# Tests that need PostgreSQL take the ``db`` fixture (and are marked ``db``).
# They use DATABASE_URL, which must name a database ending in "_test": the
# schema there is dropped and recreated on every run, so pointing it at the
# development database would wipe it. Without a reachable *_test database
# these tests are skipped, not failed.


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    from sqlalchemy import create_engine
    from sqlalchemy.exc import OperationalError

    import app.database.models  # noqa: F401  (registers every table in Base.metadata)
    from app.config import get_settings
    from app.database.conf.alch_conf import Base

    engine = create_engine(get_settings().database_url)
    name = engine.url.database or ""
    if not name.endswith("_test"):
        pytest.skip(f"DATABASE_URL names {name!r}; database tests need a *_test database")
    try:
        with engine.connect():
            pass
    except OperationalError:
        pytest.skip(f"PostgreSQL database {name!r} is not reachable")

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine: Engine) -> Iterator[Session]:
    """A session whose work is thrown away when the test ends.

    The whole test runs inside one outer transaction. Code under test may call
    ``commit()``: with ``join_transaction_mode="create_savepoint"`` that only
    releases a savepoint, and the rollback at the end still undoes it.
    The session is configured like the application's (``alch_conf.py``).
    """
    connection = db_engine.connect()
    outer = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()
