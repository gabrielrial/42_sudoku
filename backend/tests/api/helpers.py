"""Shared pieces for the HTTP tests in this folder."""

from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.api.cookies import ACCESS_COOKIE, REFRESH_COOKIE
from app.database.models.users import User
from app.services.auth import create_access_token
from app.services.refresh_token import issue_refresh_token

PASSWORD = "correct-horse-battery-staple"


def error_code(response: Response) -> str:
    """The ``code`` of an error answered in the common envelope (``API.md``, "Errors")."""
    code = response.json()["error"]["code"]
    assert isinstance(code, str)
    return code


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


def sign_in(client: TestClient, db: Session, user: User) -> dict[str, str]:
    """Give ``client`` a session for ``user`` without going through any sign-in endpoint.

    Issues the same two tokens a successful sign-in does and puts them in the
    client's cookie jar, as the browser would. Returns the two token values.
    The session endpoints (/me, /refresh, /logout) are tested through this, so
    their tests do not depend on how people sign in (D16: 42, not passwords).
    """
    access_token = create_access_token(user)
    refresh_token = issue_refresh_token(db, user.id)
    db.commit()
    tokens = {ACCESS_COOKIE: access_token, REFRESH_COOKIE: refresh_token}
    only_cookies(client, **tokens)
    return tokens
