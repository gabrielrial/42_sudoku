"""Time, in one place.

Every day boundary in this application is a Europe/Berlin calendar day (D1), and
every one of them is somewhere to get DST wrong. All of that lives here so it is
written once and tested once.

Storage is always UTC; the Berlin rule is applied only when deciding which
calendar day an instant belongs to.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

APP_TZ = ZoneInfo("Europe/Berlin")
UTC = ZoneInfo("UTC")

#: Hours past midnight after which a previous day's session is closed
#: unconditionally (DECISIONS.md Q1).
ROLLOVER_GRACE_HOURS = 2


def now() -> datetime:
    """The current instant, timezone-aware, in UTC."""
    return datetime.now(tz=UTC)


def today(at: datetime | None = None) -> date:
    """The Europe/Berlin calendar day that ``at`` (default: now) falls on."""
    return (at or now()).astimezone(APP_TZ).date()


def day_start(day: date) -> datetime:
    """Midnight at the start of ``day`` in Berlin, as a UTC instant."""
    return datetime.combine(day, time.min, tzinfo=APP_TZ).astimezone(UTC)


def day_end(day: date) -> datetime:
    """Midnight at the end of ``day`` in Berlin, as a UTC instant.

    Not simply ``day_start(day) + 24h``: on DST transition days the Berlin day is
    23 or 25 hours long.
    """
    return day_start(day + timedelta(days=1))


def rollover_deadline(day: date) -> datetime:
    """The hard cutoff for sessions belonging to ``day`` (Q1).

    Two hours after the Berlin midnight that ends ``day``. No session on that
    date survives past this instant, whatever its activity.
    """
    return day_end(day) + timedelta(hours=ROLLOVER_GRACE_HOURS)
