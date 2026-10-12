"""The login's memory between /login and /callback (``app/services/oauth_pkce.py``).

``start_login`` opens a login: it saves a fresh ``state`` with its PKCE
``code_verifier`` and returns what travels through the browser (the state and
the verifier's challenge). ``finish_login`` closes it: it hands back the
verifier once, and only for a state that was issued and has not expired.

Database tests run against PostgreSQL through the ``db`` fixture, inside a
transaction that is rolled back afterwards.
"""

import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.database.models.oauth_states import OAuthState
from app.services.oauth_pkce import (
    STATE_LIFETIME,
    InvalidOAuthState,
    code_challenge,
    finish_login,
    generate_pkce_pair,
    start_login,
)

# RFC 7636, appendix B: the standard's own example of a verifier and its S256 challenge.
RFC_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
RFC_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

# RFC 7636, section 4.1: 43 to 128 "unreserved" characters.
VERIFIER_FORMAT = re.compile(r"[A-Za-z0-9\-._~]{43,128}")


# --- helpers -----------------------------------------------------------------


def _open_login(db: Session) -> tuple[str, str]:
    """What /login will do: open a login, then commit it."""
    state, challenge = start_login(db)
    db.commit()
    return state, challenge


def _save_expired(db: Session, state: str) -> None:
    db.add(
        OAuthState(
            state=state,
            code_verifier=RFC_VERIFIER,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    db.commit()


# --- the challenge (no database) ---------------------------------------------


def test_the_challenge_matches_the_rfc_example() -> None:
    # If this fails, 42 would compute a different challenge and (if it checks
    # PKCE) refuse every login; if it does not check, nobody would ever notice.
    assert code_challenge(RFC_VERIFIER) == RFC_CHALLENGE


def test_a_generated_verifier_has_the_rfc_format() -> None:
    verifier, _ = generate_pkce_pair()

    assert VERIFIER_FORMAT.fullmatch(verifier)


def test_a_generated_pair_belongs_together() -> None:
    verifier, challenge = generate_pkce_pair()

    assert challenge == code_challenge(verifier)


def test_every_pair_is_new() -> None:
    assert generate_pkce_pair()[0] != generate_pkce_pair()[0]


# --- start_login -------------------------------------------------------------


@pytest.mark.db
def test_start_saves_the_verifier_behind_the_challenge(db: Session) -> None:
    state, challenge = _open_login(db)

    row = db.get(OAuthState, state)
    assert row is not None
    assert code_challenge(row.code_verifier) == challenge
    assert row.code_verifier != challenge  # the verifier itself never leaves the server


@pytest.mark.db
def test_start_gives_every_login_its_own_state(db: Session) -> None:
    first, _ = _open_login(db)
    second, _ = _open_login(db)

    assert first != second


@pytest.mark.db
def test_start_sets_the_lifetime(db: Session) -> None:
    before = datetime.now(UTC)
    state, _ = _open_login(db)
    after = datetime.now(UTC)

    row = db.get(OAuthState, state)
    assert row is not None
    assert before + STATE_LIFETIME <= row.expires_at <= after + STATE_LIFETIME


@pytest.mark.db
def test_start_clears_expired_logins(db: Session) -> None:
    # Somebody pressed "Sign in with 42" and closed the tab: nothing else removes the row.
    _save_expired(db, "abandoned")

    state, _ = _open_login(db)

    db.expunge_all()  # forget the cached objects: read the table itself
    assert db.get(OAuthState, "abandoned") is None
    assert db.get(OAuthState, state) is not None


# --- finish_login ------------------------------------------------------------


@pytest.mark.db
def test_finish_returns_the_saved_verifier(db: Session) -> None:
    state, challenge = _open_login(db)

    verifier = finish_login(db, state)

    assert code_challenge(verifier) == challenge


@pytest.mark.db
def test_a_state_works_only_once(db: Session) -> None:
    state, _ = _open_login(db)
    finish_login(db, state)
    db.commit()

    assert db.get(OAuthState, state) is None
    with pytest.raises(InvalidOAuthState):
        finish_login(db, state)


@pytest.mark.db
def test_an_unknown_state_is_rejected(db: Session) -> None:
    with pytest.raises(InvalidOAuthState):
        finish_login(db, "never-issued")


@pytest.mark.db
def test_an_empty_state_is_rejected(db: Session) -> None:
    with pytest.raises(InvalidOAuthState):
        finish_login(db, "")


@pytest.mark.db
def test_an_expired_state_is_rejected(db: Session) -> None:
    _save_expired(db, "too-late")

    with pytest.raises(InvalidOAuthState):
        finish_login(db, "too-late")
