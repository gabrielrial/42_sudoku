"""Fixtures for the game API tests. Opt in per module:
``pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fixed_clock")]``."""

from collections.abc import Callable
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import clock
from app.database.models.puzzles import Puzzle
from app.database.models.users import User
from tests.api.games import DAY, NOW, make_puzzle
from tests.api.helpers import sign_in


@pytest.fixture
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> Callable[[datetime], None]:
    """``app.clock.now`` fixed at ``NOW``; call the fixture's value to move it."""

    def set_now(instant: datetime) -> None:
        monkeypatch.setattr(clock, "now", lambda: instant)

    set_now(NOW)
    return set_now


@pytest.fixture
def week(db: Session) -> dict[tuple[date, str], Puzzle]:
    """Yesterday's, today's and tomorrow's puzzles, all three difficulties."""
    return {
        (day, d): make_puzzle(db, day, d)
        for day in (DAY - timedelta(days=1), DAY, DAY + timedelta(days=1))
        for d in ("easy", "medium", "hard")
    }


@pytest.fixture
def signed_in(db: Session, db_client: TestClient, user: User) -> TestClient:
    sign_in(db_client, db, user)
    return db_client
