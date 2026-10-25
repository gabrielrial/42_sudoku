"""``session_status``: in progress, completed, or closed by the rollover (``GAME_RULES.md`` §3).

Every case states the instant and the last contact; nothing reads a clock.
Times are written in Berlin wall-clock time where that is unambiguous, and in
UTC around the two nights a year when Berlin's clock jumps.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.clock import UTC
from app.config import get_settings
from app.services.game_status import Status, Thresholds, session_status

BERLIN = ZoneInfo("Europe/Berlin")
Q1 = Thresholds(inactivity=timedelta(minutes=15), grace=timedelta(hours=2))
SEPT_9 = date(2026, 9, 9)


def berlin(day: int, hour: int, minute: int = 0, second: int = 0, month: int = 9) -> datetime:
    return datetime(2026, month, day, hour, minute, second, tzinfo=BERLIN)


def status(
    now: datetime,
    last_activity: datetime,
    puzzle_date: date = SEPT_9,
    completed_at: datetime | None = None,
) -> Status:
    return session_status(
        puzzle_date=puzzle_date,
        completed_at=completed_at,
        last_activity_at=last_activity,
        now=now,
        thresholds=Q1,
    )


def test_the_thresholds_are_q1s() -> None:
    assert Thresholds.from_settings(get_settings()) == Q1


# --- completed ----------------------------------------------------------------------------


def test_a_completed_game_is_completed_whatever_the_time() -> None:
    # Finished at 00:05 on the 10th, looked at a week later.
    finished = berlin(10, 0, 5)

    assert status(berlin(17, 12), finished, completed_at=finished) is Status.COMPLETED


# --- within its own day, a game never closes ---------------------------------------------


def test_a_game_of_today_stays_open_however_idle() -> None:
    # Started at 08:00, left alone all day: no time pressure, no penalty.
    assert status(berlin(9, 23, 59), berlin(9, 8, 0)) is Status.IN_PROGRESS


# --- the night after: the example of GAME_RULES.md §3 ---------------------------------------


def test_still_playing_after_midnight_continues() -> None:
    # Started 23:55 on the 9th, still sending inputs at 00:10 on the 10th.
    assert status(berlin(10, 0, 10), berlin(10, 0, 9, 30)) is Status.IN_PROGRESS


def test_left_and_back_the_next_day_is_closed() -> None:
    # Last contact 23:58 on the 9th, back at 09:00 on the 10th.
    assert status(berlin(10, 9, 0), berlin(9, 23, 58)) is Status.CLOSED


# --- the inactivity threshold ----------------------------------------------------------------


def test_exactly_fifteen_idle_minutes_is_still_open() -> None:
    assert status(berlin(10, 0, 45), berlin(10, 0, 30)) is Status.IN_PROGRESS


def test_more_than_fifteen_idle_minutes_closes() -> None:
    assert status(berlin(10, 0, 45, 1), berlin(10, 0, 30)) is Status.CLOSED


def test_the_check_is_continuous_not_once_at_midnight() -> None:
    # Idle from 00:30: closed at 00:45, not given the rest of the window to 02:00.
    last = berlin(10, 0, 30)
    assert status(berlin(10, 0, 44), last) is Status.IN_PROGRESS
    assert status(berlin(10, 0, 46), last) is Status.CLOSED


def test_idle_since_before_midnight_counts_across_it() -> None:
    # Last contact 23:50, now 00:06: 16 minutes idle, midnight or not.
    assert status(berlin(10, 0, 6), berlin(9, 23, 50)) is Status.CLOSED


# --- the hard cap at 02:00 ---------------------------------------------------------------------


def test_active_until_the_deadline_is_open() -> None:
    assert status(berlin(10, 1, 59, 59), berlin(10, 1, 59, 50)) is Status.IN_PROGRESS


def test_the_deadline_closes_even_an_active_game() -> None:
    # A heartbeat a second ago changes nothing: no traffic extends a game past 02:00.
    assert status(berlin(10, 2, 0), berlin(10, 1, 59, 59)) is Status.CLOSED


def test_a_game_from_two_days_ago_is_closed() -> None:
    assert status(berlin(11, 12), berlin(11, 11, 59, 59)) is Status.CLOSED


# --- the two nights a year the clock jumps ----------------------------------------------------


@pytest.mark.parametrize(
    ("puzzle_date", "deadline_utc", "berlin_wall_clock"),
    [
        # Puzzles of the two days that are not 24 hours long. "Start of the day
        # plus 24 hours plus 2" would be an hour off on both.
        # 25 October 2026 lasts 25 hours: it ends at 00:00 CET on the 26th,
        # 23:00 UTC; the deadline is 02:00 CET, 01:00 UTC.
        (date(2026, 10, 25), datetime(2026, 10, 26, 1, 0, tzinfo=UTC), (2, 0)),
        # 29 March 2026 lasts 23 hours: it ends at 00:00 CEST on the 30th,
        # 22:00 UTC; the deadline is 02:00 CEST, 00:00 UTC.
        (date(2026, 3, 29), datetime(2026, 3, 30, 0, 0, tzinfo=UTC), (2, 0)),
        # Puzzles of the days before, whose grace period runs into the jump.
        # 24 -> 25 October: 02:00 CEST is 00:00 UTC; the clock only goes back
        # (03:00 CEST -> 02:00 CET) an hour after the deadline.
        (date(2026, 10, 24), datetime(2026, 10, 25, 0, 0, tzinfo=UTC), (2, 0)),
        # 28 -> 29 March: 02:00 never happens (02:00 CET -> 03:00 CEST). Two
        # hours of real time after midnight is 03:00 CEST, 01:00 UTC.
        (date(2026, 3, 28), datetime(2026, 3, 29, 1, 0, tzinfo=UTC), (3, 0)),
    ],
    ids=[
        "puzzle of the 25-hour day",
        "puzzle of the 23-hour day",
        "grace runs into the clock going back",
        "grace runs into the clock going forward",
    ],
)
def test_the_deadline_is_two_real_hours_after_midnight(
    puzzle_date: date, deadline_utc: datetime, berlin_wall_clock: tuple[int, int]
) -> None:
    second = timedelta(seconds=1)
    assert status(deadline_utc - second, deadline_utc - 2 * second, puzzle_date) is (
        Status.IN_PROGRESS
    )
    assert status(deadline_utc, deadline_utc - second, puzzle_date) is Status.CLOSED
    local = deadline_utc.astimezone(BERLIN)
    assert (local.hour, local.minute) == berlin_wall_clock
