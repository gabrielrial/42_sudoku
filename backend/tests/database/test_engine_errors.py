"""A database error never quotes the values that were bound to the statement."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.database.conf.alch_conf import make_engine

pytestmark = pytest.mark.db


def test_a_failed_statement_does_not_quote_its_parameters(db: Session) -> None:
    engine = make_engine(db.get_bind().engine.url)
    try:
        with engine.connect() as connection, pytest.raises(ProgrammingError) as failure:
            connection.execute(
                text("SELECT 1 FROM no_such_table WHERE x = :secret"), {"secret": "SECRETSTATE"}
            )
    finally:
        engine.dispose()

    assert "no_such_table" in str(failure.value)  # it is the error we meant to cause
    assert "SECRETSTATE" not in str(failure.value)
