"""Liveness and readiness.

``/api/health`` answers without touching anything, so it works before the
database exists. ``/api/health/db`` is the one that proves compose wired the
services together.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.clock import today
from app.db import get_session
from app.errors import APIError

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health() -> dict[str, str]:
    return {"status": "ok", "date": today().isoformat()}


@router.get("/db")
def health_db(session: Annotated[Session, Depends(get_session)]) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - exercised only when the DB is down
        raise APIError(
            "database_unavailable",
            "The database is not reachable.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    return {"status": "ok"}
