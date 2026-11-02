"""Keeps the sign-in's authorization code and ``state`` out of the access log.

uvicorn's access log writes the whole URL of every request, and 42 sends both
in the query string of the callback (``SECURITY.md``: never log authorization
codes). The rest of the line stays: it is what a failed sign-in is diagnosed by.
"""

import logging

ACCESS_LOGGER = "uvicorn.access"
CALLBACK_PATH = "/api/auth/callback"


def _without_query(arg: object) -> object:
    if isinstance(arg, str) and arg.partition("?")[0] == CALLBACK_PATH:
        return CALLBACK_PATH
    return arg


class HideCallbackQuery(logging.Filter):
    """Drops the query from the callback's URL, wherever the record carries it."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(_without_query(arg) for arg in record.args)
        return True


_FILTER = HideCallbackQuery()


def hide_callback_query() -> None:
    """Safe to call repeatedly: a logger keeps one copy of the same filter."""
    logging.getLogger(ACCESS_LOGGER).addFilter(_FILTER)
