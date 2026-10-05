"""Every error leaves the API in the same shape (``API.md``, "Errors"):

    {"error": {"code": "...", "message": "..."}}

These cover the errors nobody raises by hand: FastAPI's own 404 for an unknown
route and 405 for a known route with the wrong method. They need no database.
"""

from fastapi.testclient import TestClient


def _assert_envelope(body: dict[str, object], code: str) -> None:
    assert set(body) == {"error"}  # no FastAPI-style "detail" next to it
    error = body["error"]
    assert isinstance(error, dict)
    assert set(error) == {"code", "message"}
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]


def test_unknown_route_uses_the_error_envelope(client: TestClient) -> None:
    response = client.get("/api/nope")

    assert response.status_code == 404
    _assert_envelope(response.json(), "not_found")


def test_wrong_method_uses_the_error_envelope(client: TestClient) -> None:
    response = client.put("/api/health")

    assert response.status_code == 405
    _assert_envelope(response.json(), "method_not_allowed")


def test_wrong_method_keeps_the_allow_header(client: TestClient) -> None:
    # A 405 must say which methods are allowed; the handler must pass the
    # exception's headers through, not drop them.
    response = client.put("/api/health")

    assert "GET" in response.headers["allow"]
