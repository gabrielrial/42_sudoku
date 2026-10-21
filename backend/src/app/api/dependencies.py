from typing import Annotated

from fastapi import Cookie, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.cookies import ACCESS_COOKIE
from app.config import Settings, get_settings
from app.database.conf.dependencies import get_db
from app.database.models.users import User
from app.errors import APIError
from app.services.auth import not_authenticated, user_from_access_token
from app.services.identity_provider import (
    FAKE_LOGIN,
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


def get_provider(
    settings: Annotated[Settings, Depends(get_settings)],
    as_login: Annotated[str | None, Query(alias="as", include_in_schema=False)] = None,
) -> IdentityProvider:
    """The identity provider the settings ask for: the fake one, or 42.

    In fake mode ``?as=<login>`` on ``/login`` chooses the made-up account to
    sign in as (D19), so two users can be tried against each other by hand.
    With the real provider it is ignored: 42 decides who signs in.
    """
    if settings.auth_fake_provider_enabled:
        if as_login is None:
            return FakeIdentityProvider()
        if not FAKE_LOGIN.fullmatch(as_login):
            raise APIError(
                "invalid_request",
                "?as= must be 1-32 characters of a-z, 0-9 and '-'.",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        return FakeIdentityProvider(as_login)

    return RealIdentityProvider(
        client_id=settings.fortytwo_client_id,
        client_secret=settings.fortytwo_client_secret,
        redirect_uri=settings.fortytwo_redirect_uri,
    )


ProviderDep = Annotated[IdentityProvider, Depends(get_provider)]
