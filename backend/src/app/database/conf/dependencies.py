from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.database.conf.alch_conf import SessionFactory


def get_db() -> Iterator[Session]:
    db = SessionFactory()
    try:
        yield db
    finally:
        db.close()
