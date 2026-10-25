from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

_settings = get_settings()


def make_engine(url: str, **kwargs: Any) -> Engine:
    """An engine whose every connection uses UTC, whatever the server's default.

    PostgreSQL stores a ``timestamptz`` as an instant, but hands it back labelled
    with the session's time zone, and Python subtracts two datetimes with the
    same zone as wall-clock times. In a Europe/Berlin session, 23:30Z to 01:30Z
    on the night summer time ends comes out as one hour, not two.

    A managed database, ``ALTER DATABASE ... SET timezone`` or ``PGTZ`` could
    switch the zone without anyone noticing. A startup option is not enough:
    ``PGTZ`` overrides ``options=-c timezone=UTC``. So every new connection
    sets the zone itself, once it is open, where nothing outside can undo it.
    """
    engine = create_engine(url, pool_pre_ping=True, **kwargs)
    event.listen(engine, "connect", _use_utc)
    return engine


def _use_utc(dbapi_connection: Any, _record: Any) -> None:
    with dbapi_connection.cursor() as cursor:
        cursor.execute("SET TIME ZONE 'UTC'")
    # Committed, or the pool's first rollback would undo it.
    dbapi_connection.commit()


engine = make_engine(_settings.database_url)

SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass
