import base64
import hashlib
import secrets
import string
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.database.models.oauth_states import OAuthState

STATE_LIFETIME = timedelta(minutes=10)


class InvalidOAuthState(Exception):
    """The callback's state was never issued, was already used, or expired."""


def code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def generate_pkce_pair() -> tuple[str, str]:
    allowed_chars = string.ascii_letters + string.digits + "-._~"
    code_verifier = "".join(secrets.choice(allowed_chars) for _ in range(128))
    return code_verifier, code_challenge(code_verifier)


def start_login(db: Session) -> tuple[str, str]:

    now = datetime.now(UTC)
    db.execute(delete(OAuthState).where(OAuthState.expires_at < now))

    state = secrets.token_urlsafe(32)
    verifier, challenge = generate_pkce_pair()
    db.add(OAuthState(state=state, code_verifier=verifier, expires_at=now + STATE_LIFETIME))
    return state, challenge


def finish_login(db: Session, state: str) -> str:
    row = db.get(OAuthState, state, with_for_update=True)
    if row is None or row.expires_at <= datetime.now(UTC):
        raise InvalidOAuthState
    db.delete(row)
    return row.code_verifier
