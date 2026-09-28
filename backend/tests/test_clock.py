"""Day boundaries, including the two days a year they are not 24 hours long.

Germany moves to summer time on the last Sunday of March and back on the last
Sunday of October. Those two dates are where naive date arithmetic breaks, so
they are tested explicitly rather than trusted.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.clock import UTC, day_end, day_start, rollover_deadline, today

BERLIN = ZoneInfo("Europe/Berlin")


def test_today_uses_berlin_not_utc():
    # 22:30 UTC on 8 September is already 00:30 on 9 September in Berlin.
    at = datetime(2026, 9, 8, 22, 30, tzinfo=UTC)
    assert today(at) == date(2026, 9, 9)


def test_today_just_before_midnight_berlin():
    at = datetime(2026, 9, 8, 23, 59, 59, tzinfo=BERLIN)
    assert today(at) == date(2026, 9, 8)


def test_ordinary_day_is_24_hours():
    day = date(2026, 9, 9)
    assert day_end(day) - day_start(day) == timedelta(hours=24)


def test_spring_forward_day_is_23_hours():
    # 29 March 2026: clocks go 02:00 -> 03:00, so the Berlin day is short.
    day = date(2026, 3, 29)
    assert day_end(day) - day_start(day) == timedelta(hours=23)


def test_autumn_back_day_is_25_hours():
    # 25 October 2026: 03:00 -> 02:00, so the Berlin day is long.
    day = date(2026, 10, 25)
    assert day_end(day) - day_start(day) == timedelta(hours=25)


def test_rollover_deadline_is_two_hours_after_the_day_ends():
    day = date(2026, 9, 9)
    assert rollover_deadline(day) - day_end(day) == timedelta(hours=2)


def test_rollover_deadline_is_0200_berlin_the_next_morning():
    deadline = rollover_deadline(date(2026, 9, 9)).astimezone(BERLIN)
    assert (deadline.date(), deadline.hour, deadline.minute) == (date(2026, 9, 10), 2, 0)


def test_rollover_deadline_across_spring_forward():
    # The night of 28->29 March loses an hour: 02:00 does not exist, so the
    # deadline lands at 03:00 local time. The point is that it is still exactly
    # two hours of real elapsed time after midnight.
    day = date(2026, 3, 28)
    assert rollover_deadline(day) - day_end(day) == timedelta(hours=2)
