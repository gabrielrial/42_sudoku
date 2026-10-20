"""The 42 side of the login (``app/services/identity_provider.py``).

No network: ``FakeFortyTwo`` answers for 42 through an ``httpx.MockTransport``
and records every request, so the tests can check exactly what would have been
sent. No database either.

The ``/v2/me`` answers below are built from the fields the code reads, not
copied from a real response: 42's documentation could not be checked. They are
to be replaced by a real response with the personal data removed.
"""

from collections.abc import Callable
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.services.identity_provider import (
    AUTHORIZE_URL,
    ME_URL,
    TOKEN_URL,
    FakeIdentityProvider,
    Identity,
    IdentityProviderError,
    NoPrimaryCampus,
    RealIdentityProvider,
)

CLIENT_ID = "client-id-123"
CLIENT_SECRET = "client-secret-456"
REDIRECT_URI = "http://localhost:8000/api/auth/callback"
CODE = "code-from-42"
VERIFIER = "v" * 64
ACCESS_TOKEN = "token-from-42"

ME: dict[str, object] = {
    "id": 98765,
    "login": "ana",
    "email": "ana@student.42berlin.de",  # present in the answer, never kept
    "campus_users": [
        {"id": 1, "user_id": 98765, "campus_id": 21, "is_primary": False},
        {"id": 2, "user_id": 98765, "campus_id": 51, "is_primary": True},
    ],
    "campus": [{"id": 21, "name": "Paris"}, {"id": 51, "name": "Berlin"}],
}


def _query(url: str) -> dict[str, str]:
    """A URL's query as {name: value}; fails if a name appears twice."""
    parsed = parse_qs(urlsplit(url).query, keep_blank_values=True, strict_parsing=True)
    assert all(len(values) == 1 for values in parsed.values())
    return {name: values[0] for name, values in parsed.items()}


Handler = Callable[[httpx.Request], httpx.Response]


class FakeFortyTwo:
    """Plays 42's token and ``/v2/me`` endpoints, and keeps what it was sent."""

    def __init__(self, me: object = ME) -> None:
        self.requests: list[httpx.Request] = []
        self.token: Handler = lambda _: httpx.Response(200, json={"access_token": ACCESS_TOKEN})
        self.me: Handler = lambda _: httpx.Response(200, json=me)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url == TOKEN_URL:
            return self.token(request)
        if request.url == ME_URL:
            return self.me(request)
        return httpx.Response(404)

    def provider(self) -> RealIdentityProvider:
        return RealIdentityProvider(
            CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, transport=httpx.MockTransport(self)
        )


def _sign_in(fake: FakeFortyTwo) -> Identity:
    return fake.provider().identity_from_code(CODE, VERIFIER)


# --- the authorize URL ---------------------------------------------------------


def test_the_authorize_url_goes_to_42() -> None:
    url = FakeFortyTwo().provider().authorize_url("some-state", "some-challenge")

    assert url.split("?")[0] == AUTHORIZE_URL


def test_the_authorize_url_carries_every_parameter() -> None:
    url = FakeFortyTwo().provider().authorize_url("some-state", "some-challenge")

    assert _query(url) == {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "public",
        "state": "some-state",
        "code_challenge": "some-challenge",
        "code_challenge_method": "S256",
    }


def test_the_authorize_url_is_encoded() -> None:
    # Pasted in raw, the "&" would end the state early and start a new parameter.
    url = FakeFortyTwo().provider().authorize_url("a&scope=evil", "c+/=")

    query = _query(url)
    assert query["state"] == "a&scope=evil"
    assert query["code_challenge"] == "c+/="
    assert query["scope"] == "public"


# --- the code exchange -----------------------------------------------------------


def test_the_code_exchange_is_a_form_post_with_the_verifier() -> None:
    fake = FakeFortyTwo()

    _sign_in(fake)

    exchange = fake.requests[0]
    assert exchange.method == "POST"
    assert exchange.url == TOKEN_URL
    assert exchange.headers["content-type"] == "application/x-www-form-urlencoded"
    assert {k: v[0] for k, v in parse_qs(exchange.content.decode()).items()} == {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": CODE,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": VERIFIER,
    }


def test_me_is_read_with_the_token_from_the_exchange() -> None:
    fake = FakeFortyTwo()

    _sign_in(fake)

    me = fake.requests[1]
    assert me.method == "GET"
    assert me.url == ME_URL
    assert me.headers["authorization"] == f"Bearer {ACCESS_TOKEN}"
    assert len(fake.requests) == 2


def test_every_call_to_42_has_a_timeout() -> None:
    fake = FakeFortyTwo()

    _sign_in(fake)

    for request in fake.requests:
        timeout = request.extensions["timeout"]
        assert all(timeout[kind] is not None for kind in ("connect", "read", "write", "pool"))


# --- reading /v2/me ---------------------------------------------------------------


def test_the_identity_comes_from_v2_me() -> None:
    assert _sign_in(FakeFortyTwo()) == Identity(
        intra_id=98765, login="ana", campus_id=51, campus_name="Berlin"
    )


def test_the_campus_is_the_primary_one_wherever_it_is_listed() -> None:
    me = dict(ME, campus=[{"id": 51, "name": "Berlin"}, {"id": 21, "name": "Paris"}])

    assert _sign_in(FakeFortyTwo(me)).campus_name == "Berlin"


def test_an_account_without_a_primary_campus_is_refused() -> None:
    me = dict(ME, campus_users=[{"campus_id": 21, "is_primary": False}])

    with pytest.raises(NoPrimaryCampus):
        _sign_in(FakeFortyTwo(me))


def test_a_primary_campus_missing_from_the_campus_list_is_refused() -> None:
    me = dict(ME, campus=[{"id": 21, "name": "Paris"}])

    with pytest.raises(IdentityProviderError):
        _sign_in(FakeFortyTwo(me))


# --- 42 failing -------------------------------------------------------------------


def _raises(exc: Exception) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return handler


FAILURES: dict[str, Callable[[FakeFortyTwo], None]] = {
    "code refused": lambda f: setattr(
        f, "token", lambda _: httpx.Response(400, json={"error": "invalid_grant"})
    ),
    "token endpoint down": lambda f: setattr(f, "token", lambda _: httpx.Response(503)),
    "token answer not JSON": lambda f: setattr(
        f, "token", lambda _: httpx.Response(200, text="<html>")
    ),
    "no access_token": lambda f: setattr(
        f, "token", lambda _: httpx.Response(200, json={"token_type": "bearer"})
    ),
    "me refused": lambda f: setattr(f, "me", lambda _: httpx.Response(401)),
    "me not JSON": lambda f: setattr(f, "me", lambda _: httpx.Response(200, text="")),
    "me without login": lambda f: setattr(
        f, "me", lambda _: httpx.Response(200, json={k: v for k, v in ME.items() if k != "login"})
    ),
    "unreachable": lambda f: setattr(f, "token", _raises(httpx.ConnectError("refused"))),
    "too slow": lambda f: setattr(f, "me", _raises(httpx.ReadTimeout("timed out"))),
}


@pytest.mark.parametrize("break_42", FAILURES.values(), ids=FAILURES.keys())
def test_every_failure_of_42_is_an_identity_provider_error(
    break_42: Callable[[FakeFortyTwo], None],
) -> None:
    fake = FakeFortyTwo()
    break_42(fake)

    with pytest.raises(IdentityProviderError) as exc:
        _sign_in(fake)

    # The message ends up in logs: no secret, code, verifier or token in it.
    for secret in (CLIENT_SECRET, CODE, VERIFIER, ACCESS_TOKEN):
        assert secret not in str(exc.value)


def test_a_refused_code_does_not_reach_v2_me() -> None:
    fake = FakeFortyTwo()
    FAILURES["code refused"](fake)

    with pytest.raises(IdentityProviderError):
        _sign_in(fake)

    assert [r.url for r in fake.requests] == [TOKEN_URL]


# --- the fake provider ----------------------------------------------------------------


def test_the_fake_sends_the_browser_straight_to_the_callback() -> None:
    url = FakeIdentityProvider().authorize_url("some-state", "some-challenge")

    assert urlsplit(url).path == "/api/auth/callback"
    assert not urlsplit(url).netloc  # a path: same origin as /login, whatever it is
    assert _query(url)["state"] == "some-state"


def test_the_fake_identity_cannot_be_a_real_42_account() -> None:
    identity = FakeIdentityProvider().identity_from_code("anything", VERIFIER)

    assert identity.intra_id < 0  # 42's ids are positive
