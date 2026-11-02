"""The access log never carries the sign-in's authorization code or ``state``."""

import logging

from uvicorn.logging import AccessFormatter

from app.access_log import ACCESS_LOGGER, CALLBACK_PATH, HideCallbackQuery
from app.main import create_app


def _line(url: str) -> str:
    """The line uvicorn writes for a request, through its own formatter."""
    record = logging.LogRecord(
        name=ACCESS_LOGGER,
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:1234", "GET", url, "1.1", 302),
        exc_info=None,
    )
    assert HideCallbackQuery().filter(record) is True  # the line is kept
    return AccessFormatter(use_colors=False).format(record)


def test_the_callback_is_logged_without_its_code_and_state() -> None:
    line = _line(f"{CALLBACK_PATH}?code=SECRETCODE&state=SECRETSTATE")

    assert "SECRETCODE" not in line
    assert "SECRETSTATE" not in line
    assert f"GET {CALLBACK_PATH} HTTP/1.1" in line
    assert "302" in line


def test_an_error_from_42_is_hidden_the_same_way() -> None:
    line = _line(f"{CALLBACK_PATH}?error=access_denied&state=SECRETSTATE")

    assert "SECRETSTATE" not in line


def test_other_urls_keep_their_query() -> None:
    assert "/api/auth/login?as=someone" in _line("/api/auth/login?as=someone")
    assert f"{CALLBACK_PATH}-not?code=1" in _line(f"{CALLBACK_PATH}-not?code=1")


def test_the_application_installs_the_filter_once() -> None:
    create_app()
    create_app()

    installed = logging.getLogger(ACCESS_LOGGER).filters
    assert sum(isinstance(f, HideCallbackQuery) for f in installed) == 1
