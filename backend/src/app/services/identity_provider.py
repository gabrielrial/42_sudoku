"""Who signed in: the 42 side of the login (``API.md``, Authentication).

Two implementations behind one interface, so the routes never know which one
they talk to:

- ``RealIdentityProvider`` sends the browser to 42, exchanges the code it gets
  back, and reads ``/v2/me``.
- ``FakeIdentityProvider`` skips 42 entirely, so local development and the
  tests never call it (``DECISIONS.md`` A3). ``config.py`` refuses it in
  production.

PKCE (``DECISIONS.md`` D18): the authorize URL carries the S256 challenge, the
code exchange carries the verifier. Both are made by ``oauth_pkce.py``; this
module only puts them where 42 expects them.

When two accounts claim one login (``DATA_MODEL.md``, ``users``), the server
asks 42 for the other account's current login with ``GET /v2/users/:id``,
using an application token (client credentials, RFC 6749 section 4.4) that is
fetched for that one call and never stored (D11). Developer-checked: 42
serves that endpoint to an application token (2026-10-20), and issues the
token for a form-encoded ``grant_type=client_credentials`` request with the
client id and secret (2026-10-21).

What ``/v2/me`` contains is taken from the fields this code reads
(``campus_users[].is_primary``, ``campus_users[].campus_id``, ``campus[].id``,
``campus[].name``). 42's API documentation sits behind the intra login and
could not be checked here.
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ValidationError

AUTHORIZE_URL = "https://api.intra.42.fr/oauth/authorize"
TOKEN_URL = "https://api.intra.42.fr/oauth/token"
ME_URL = "https://api.intra.42.fr/v2/me"
USERS_URL = "https://api.intra.42.fr/v2/users"

#: Seconds. A login waits on 42 twice; neither wait may hang a worker forever.
TIMEOUT = httpx.Timeout(10.0, connect=5.0)


@dataclass(frozen=True)
class Identity:
    """What the application keeps of a 42 account (``DATA_MODEL.md``, ``users``)."""

    intra_id: int
    login: str
    campus_id: int
    campus_name: str


class IdentityProviderError(Exception):
    """42 could not say who signed in: unreachable, refused the code, or
    answered something this code does not understand.

    The message is for logs. It never carries a token, a code or a secret.
    """


class NoPrimaryCampus(IdentityProviderError):
    """The account has no primary campus, which ``users`` requires."""


class IdentityProvider(Protocol):
    def authorize_url(self, state: str, code_challenge: str) -> str:
        """Where the browser goes to sign in: the first step of the flow."""
        ...

    def identity_from_code(self, code: str, code_verifier: str) -> Identity:
        """Exchange the code the callback received for the account behind it.

        Raises ``IdentityProviderError``.
        """
        ...

    def current_login(self, intra_id: int) -> str | None:
        """The login 42 gives that account today; ``None`` if 42 does not know it.

        Raises ``IdentityProviderError``.
        """
        ...


FAKE_LOGIN = re.compile(r"[a-z0-9-]{1,32}")
"""What the fake provider accepts as a login: short, lowercase, URL-safe."""


def fake_identity(login: str) -> Identity:
    """The made-up account behind a fake login.

    Its ``intra_id`` is negative — 42's ids are positive, so a fake user can
    never be a real one — and derived from the login, so the same login is the
    same user on every sign-in. It fits ``users.intra_id`` (``INTEGER``).
    """
    digest = hashlib.sha256(login.encode()).digest()
    intra_id = -(int.from_bytes(digest[:4], "big") >> 1) - 1  # -1 .. -2**31
    return Identity(intra_id=intra_id, login=login, campus_id=-1, campus_name="Fake campus")


class FakeIdentityProvider:
    """Signs in as a made-up account, without leaving the server (A3).

    Which account is chosen at ``/login`` (``?as=<login>``, D19) and travels to
    the callback inside the code, as a real code would. The authorize URL is
    the callback itself, as a path: the browser stays on whichever origin it
    used for ``/login``, so no host or port is assumed.
    """

    DEFAULT_LOGIN = "fake-user"

    def __init__(self, login: str = DEFAULT_LOGIN) -> None:
        if not FAKE_LOGIN.fullmatch(login):
            raise ValueError("a fake login is 1-32 characters of a-z, 0-9 and '-'")
        self.login = login

    def authorize_url(self, state: str, code_challenge: str) -> str:
        return "/api/auth/callback?" + urlencode({"code": f"fake:{self.login}", "state": state})

    def identity_from_code(self, code: str, code_verifier: str) -> Identity:
        login = code.removeprefix("fake:")
        if login == code or not FAKE_LOGIN.fullmatch(login):
            raise IdentityProviderError("not a code the fake provider issued")
        return fake_identity(login)

    def current_login(self, intra_id: int) -> str | None:
        return None  # the fake has no directory of accounts


# --- the shapes 42 answers with; anything not listed here is ignored ---------


class _Token(BaseModel):
    access_token: str


class _CampusUser(BaseModel):
    campus_id: int
    is_primary: bool


class _Campus(BaseModel):
    id: int
    name: str


class _User(BaseModel):
    login: str


class _Me(BaseModel):
    id: int
    login: str
    campus_users: list[_CampusUser]
    campus: list[_Campus]


class RealIdentityProvider:
    """The 42 intra, through the authorization code flow (RFC 6749, section 4.1).

    ``transport`` exists for the tests, which answer for 42 with an
    ``httpx.MockTransport``; in the application it is left as ``None``.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self._transport = transport

    def authorize_url(self, state: str, code_challenge: str) -> str:
        query = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "scope": "public",
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{AUTHORIZE_URL}?{query}"

    def identity_from_code(self, code: str, code_verifier: str) -> Identity:
        try:
            with httpx.Client(timeout=TIMEOUT, transport=self._transport) as client:
                token = self._exchange(client, code, code_verifier)
                me = self._me(client, token)
        except httpx.HTTPError as exc:
            # Only the exception's class: its text can include the request URL.
            raise IdentityProviderError(f"42 request failed: {type(exc).__name__}") from None
        except ValidationError:
            raise IdentityProviderError("42 answered in an unexpected shape") from None
        return _identity(me)

    def current_login(self, intra_id: int) -> str | None:
        try:
            with httpx.Client(timeout=TIMEOUT, transport=self._transport) as client:
                token = self._application_token(client)
                response = client.get(
                    f"{USERS_URL}/{intra_id}", headers={"Authorization": f"Bearer {token}"}
                )
                if response.status_code == httpx.codes.NOT_FOUND:
                    return None
                response.raise_for_status()
                return _User.model_validate_json(response.content).login
        except httpx.HTTPError as exc:
            raise IdentityProviderError(f"42 request failed: {type(exc).__name__}") from None
        except ValidationError:
            raise IdentityProviderError("42 answered in an unexpected shape") from None

    def _application_token(self, client: httpx.Client) -> str:
        """A token for the application itself, not for any user (RFC 6749 section 4.4)."""
        response = client.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        response.raise_for_status()
        return _Token.model_validate_json(response.content).access_token

    def _exchange(self, client: httpx.Client, code: str, code_verifier: str) -> str:
        """The code exchange. Form-encoded, as RFC 6749 section 4.1.3 requires."""
        response = client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": self.redirect_uri,
                "code_verifier": code_verifier,
            },
        )
        response.raise_for_status()
        return _Token.model_validate_json(response.content).access_token

    def _me(self, client: httpx.Client, token: str) -> _Me:
        response = client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
        response.raise_for_status()
        return _Me.model_validate_json(response.content)


def _identity(me: _Me) -> Identity:
    """The account's primary campus, by name, from the two lists ``/v2/me`` keeps it in."""
    primary = next((cu for cu in me.campus_users if cu.is_primary), None)
    if primary is None:
        raise NoPrimaryCampus("the 42 account has no primary campus")
    campus = next((c for c in me.campus if c.id == primary.campus_id), None)
    if campus is None:
        raise IdentityProviderError("the primary campus is missing from the campus list")
    return Identity(intra_id=me.id, login=me.login, campus_id=campus.id, campus_name=campus.name)
