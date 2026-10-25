from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

_settings = get_settings()


def make_engine(url: str) -> Engine:
    """An engine whose every connection uses UTC, whatever the server's default.

    PostgreSQL stores a ``timestamptz`` as an instant, but hands it back labelled
    with the session's time zone, and Python subtracts two datetimes with the
    same zone as wall-clock times. In a Europe/Berlin session, 23:30Z to 01:30Z
    on the night summer time ends comes out as one hour, not two. A managed
    database, ``ALTER DATABASE ... SET timezone`` or ``PGTZ`` could switch it
    without anyone noticing; this cannot be switched from outside.
    """
    return create_engine(url, pool_pre_ping=True, connect_args={"options": "-c timezone=UTC"})


engine = make_engine(_settings.database_url)

SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass
