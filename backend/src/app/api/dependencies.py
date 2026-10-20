from typing import Annotated

from fastapi import Cookie, Depends
from sqlalchemy.orm import Session

from app.api.cookies import ACCESS_COOKIE
from app.config import get_settings
from app.database.conf.dependencies import get_db
from app.database.models.users import User
from app.services.auth import not_authenticated, user_from_access_token
from app.services.identity_provider import (
    FakeIdentityProvider,
    IdentityProvider,
    RealIdentityProvider,
)


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
) -> User:
    if not access_token:
        raise not_authenticated()
    return user_from_access_token(db, access_token)


def get_provider() -> IdentityProvider:
    """The identity provider the settings ask for: the fake one, or 42."""
    settings = get_settings()

    if settings.auth_fake_provider_enabled:
        return FakeIdentityProvider()

    return RealIdentityProvider(
        client_id=settings.fortytwo_client_id,
        client_secret=settings.fortytwo_client_secret,
        redirect_uri=settings.fortytwo_redirect_uri,
    )


ProviderDep = Annotated[IdentityProvider, Depends(get_provider)]
