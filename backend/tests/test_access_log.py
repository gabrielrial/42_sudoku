"""The access log never carries the sign-in's authorization code or ``state``."""

import logging
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest
from uvicorn.logging import AccessFormatter

from app.access_log import ACCESS_LOGGER, HideQueries
from app.main import create_app

CALLBACK = "/api/auth/callback"


def _line(url: str) -> str:
    """The line for a request, through uvicorn's formatter but a record built here."""
    record = logging.LogRecord(
        name=ACCESS_LOGGER,
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:1234", "GET", url, "1.1", 302),
        exc_info=None,
    )
    assert HideQueries().filter(record) is True  # the line is kept
    return AccessFormatter(use_colors=False).format(record)


def test_the_callback_is_logged_without_its_code_and_state() -> None:
    line = _line(f"{CALLBACK}?code=SECRETCODE&state=SECRETSTATE")

    assert "SECRETCODE" not in line
    assert "SECRETSTATE" not in line
    assert f"GET {CALLBACK} HTTP/1.1" in line
    assert "302" in line


@pytest.mark.parametrize(
    "path",
    [
        f"{CALLBACK}/",  # the router redirects this one, query and all
        f"/{CALLBACK}",
        CALLBACK.upper(),
        f"{CALLBACK};x=y",
        "/api/auth/./callback",
    ],
)
def test_no_spelling_of_the_path_gets_its_query_logged(path: str) -> None:
    assert "SECRETCODE" not in _line(f"{path}?code=SECRETCODE")


def test_an_error_from_42_is_hidden_the_same_way() -> None:
    assert "SECRETSTATE" not in _line(f"{CALLBACK}?error=access_denied&state=SECRETSTATE")


def test_the_application_installs_the_filter_once() -> None:
    create_app()
    create_app()

    installed = logging.getLogger(ACCESS_LOGGER).filters
    assert sum(isinstance(f, HideQueries) for f in installed) == 1


def test_a_real_uvicorn_logs_the_request_without_its_query() -> None:
    # Everything above builds the record by hand; this is the one that would
    # notice uvicorn changing how it logs, or resetting the logger's filters.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    url = f"http://127.0.0.1:{port}/api/health?code=SECRETCODE"
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                assert httpx.get(url).status_code == 200
                break
            except httpx.TransportError:
                assert time.monotonic() < deadline, "uvicorn did not start"
                time.sleep(0.1)
    finally:
        server.terminate()
        output, _ = server.communicate(timeout=30)

    assert "GET /api/health HTTP/1.1" in output
    assert "SECRETCODE" not in output
