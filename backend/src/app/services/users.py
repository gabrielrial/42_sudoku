"""Keeping ``users`` in step with 42 at every sign-in (``DATA_MODEL.md``, ``users``).

A person is their ``intra_id``, which never changes. Their ``login`` and campus
are refreshed from 42 every time they sign in.

``login`` is unique, so it can collide: 42 renames someone and gives their old
login to somebody else, and we only hear about it when the newcomer signs in.
42 is the authority on who holds a login today, so the person signing in gets
it, and the stale holder is renamed to whatever 42 calls them now. When that
cannot be found out, or that name is itself taken here, the stale holder gets
a placeholder until their own next sign-in puts the truth back. Nobody is ever
refused a sign-in because of somebody else's stale row.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.users import User
from app.services.identity_provider import Identity, IdentityProvider, IdentityProviderError

logger = logging.getLogger(__name__)


def placeholder_login(intra_id: int) -> str:
    """What a stale holder is called while their real login is unknown."""
    return f"former-{intra_id}"


def upsert_user(db: Session, identity: Identity, provider: IdentityProvider) -> User:
    """The ``users`` row for ``identity``, created or refreshed, and flushed.

    Does not commit: the caller writes the user and their session together.
    """
    _free_login(db, identity, provider)

    user = db.scalar(select(User).where(User.intra_id == identity.intra_id))
    if user is None:
        user = User(intra_id=identity.intra_id)
        db.add(user)
    user.login = identity.login
    user.campus_id = identity.campus_id
    user.campus_name = identity.campus_name
    db.flush()
    return user


def _free_login(db: Session, identity: Identity, provider: IdentityProvider) -> None:
    """If another account holds ``identity.login`` here, rename it first.

    Flushed on its own: PostgreSQL checks the unique constraint per statement,
    so the stale holder must have let go before the new holder takes it.
    """
    holder = db.scalar(
        select(User).where(User.login == identity.login, User.intra_id != identity.intra_id)
    )
    if holder is None:
        return  # the normal case: no call to 42 beyond the sign-in itself

    holder.login = _current_login(db, holder, provider) or placeholder_login(holder.intra_id)
    db.flush()
    logger.warning(
        "login taken over: intra_id %s now holds it; intra_id %s renamed",
        identity.intra_id,
        holder.intra_id,
    )


def _current_login(db: Session, holder: User, provider: IdentityProvider) -> str | None:
    """The holder's login according to 42, if it is usable here; otherwise ``None``."""
    try:
        login = provider.current_login(holder.intra_id)
    except IdentityProviderError as exc:
        logger.warning("could not ask 42 for intra_id %s's login: %s", holder.intra_id, exc)
        return None
    if login is None:
        return None  # 42 does not know the account
    # Taken here: by a third account (renaming that one too would chase a
    # chain), or still by the holder (42 contradicts the sign-in under way).
    if db.scalar(select(User.id).where(User.login == login)) is not None:
        return None
    return login
