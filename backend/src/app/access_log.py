"""Keeps the sign-in's authorization code and ``state`` out of the access log.

uvicorn's access log writes the whole URL of every request, and 42 sends both
in the query string of the callback (``SECURITY.md``: never log authorization
codes). Every query goes, not only the callback's: a path compared exactly
misses ``/api/auth/callback/``, which the router redirects with its query, so
a redirect URI registered that way would sign in and log every code.
The rest of the line stays: it is what a failed sign-in is diagnosed by.
"""

import logging

ACCESS_LOGGER = "uvicorn.access"


class HideQueries(logging.Filter):
    """Drops the query from the URL, wherever the record carries it."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                arg.partition("?")[0] if isinstance(arg, str) else arg for arg in record.args
            )
        return True


_FILTER = HideQueries()


def hide_queries() -> None:
    """Safe to call repeatedly: a logger keeps one copy of the same filter."""
    logging.getLogger(ACCESS_LOGGER).addFilter(_FILTER)
