"""Command line: ``python -m app.jobs.generate_puzzles [--days N] [--every SECONDS]``.

Makes sure today and the days after it have their puzzles (``DECISIONS.md``
Q11), then stops; with ``--every`` it does that again and again, which is how
the ``puzzles`` compose service runs it. "Today" is the Europe/Berlin day
(D1), whatever the machine's clock zone.

A round that fails outright — the database not reachable yet, or its tables
not migrated yet — is logged and tried again a minute later, not an hour.
"""

import argparse
import logging
import time
from collections.abc import Callable, Sequence

from app import clock
from app.config import get_settings
from app.database.conf.alch_conf import SessionFactory
from app.services.puzzles import Report, ensure_puzzles

logger = logging.getLogger("app.jobs.generate_puzzles")

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

RETRY_AFTER_ERROR = 60
"""Seconds before trying again after a round that failed outright."""


def run_once(days: int) -> Report:
    start = clock.today()
    with SessionFactory() as db:
        report = ensure_puzzles(db, start, days)
    logger.info(
        "puzzles from %s for %d days: %d created, %d failed",
        start,
        days,
        len(report.created),
        len(report.failed),
    )
    return report


def main(argv: Sequence[str] | None = None, sleep: Callable[[float], None] = time.sleep) -> int:
    """Exit status 0 when nothing is missing, 1 when some puzzle could not be
    made. With ``--every`` it never returns. ``sleep`` exists for the tests."""
    parser = argparse.ArgumentParser(prog="python -m app.jobs.generate_puzzles")
    parser.add_argument(
        "--days",
        type=_positive,
        default=get_settings().puzzle_days_ahead,
        help="today and the days after it (default: PUZZLE_DAYS_AHEAD)",
    )
    parser.add_argument(
        "--every", type=_positive, metavar="SECONDS", help="repeat forever, this far apart"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

    if args.every is None:
        return 1 if run_once(args.days).failed else 0

    while True:
        try:
            run_once(args.days)
        except Exception:
            logger.exception("puzzle round failed; trying again in %d s", RETRY_AFTER_ERROR)
            sleep(RETRY_AFTER_ERROR)
        else:
            sleep(args.every)


def _positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
