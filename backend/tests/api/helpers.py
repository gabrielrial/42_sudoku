"""Shared pieces for the HTTP tests in this folder."""

from fastapi.testclient import TestClient
from httpx import Response

PASSWORD = "correct-horse-battery-staple"


def login(client: TestClient, username: str, password: str) -> Response:
    # OAuth2PasswordRequestForm reads a form, not JSON.
    return client.post("/api/users/login", data={"username": username, "password": password})


def set_cookies(response: Response) -> dict[str, dict[str, str]]:
    """Each Set-Cookie header as {cookie name: {attribute: value}}.

    The cookie's own value is under "value". Attribute names are lower-cased;
    flags such as HttpOnly map to "".
    """
    cookies: dict[str, dict[str, str]] = {}
    for header in response.headers.get_list("set-cookie"):
        first, *attributes = (part.strip() for part in header.split(";"))
        name, value = first.split("=", 1)
        parsed = {"value": value}
        for attribute in attributes:
            key, _, attr_value = attribute.partition("=")
            parsed[key.lower()] = attr_value
        cookies[name] = parsed
    return cookies


def only_cookies(client: TestClient, **cookies: str) -> None:
    """Replace whatever the client's cookie jar holds with exactly these cookies."""
    client.cookies.clear()
    for name, value in cookies.items():
        client.cookies.set(name, value)
