from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.cookies import set_auth_cookies
from app.api.dependencies import get_current_user
from app.api.rate_limits import limit_login_attempts
from app.database.conf.dependencies import get_db
from app.database.models.users import User
from app.database.schema.user import UserCreate, UserPublic
from app.errors import APIError
from app.services.auth import create_access_token
from app.services.refresh_token import issue_refresh_token
from app.utils.security import DUMMY_HASH, hash_password, verify_password

router = APIRouter(prefix="/users", tags=["users"])


def _invalid_credentials() -> APIError:
    return APIError(
        "invalid_credentials", "Invalid username or password.", status.HTTP_401_UNAUTHORIZED
    )


@router.get("/me", response_model=UserPublic)
def read_me(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    return current_user


@router.post("/login", response_model=UserPublic, dependencies=[Depends(limit_login_attempts)])
def login(
    response: Response,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    user = db.query(User).filter(User.username == form.username.lower()).first()

    if len(form.password) > PASSWORD_MAX_LENGTH:
        raise _invalid_credentials()

    password = verify_password(form.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not password:
        raise _invalid_credentials()

    access_token = create_access_token(user)
    refresh_token = issue_refresh_token(db, user.id)
    db.commit()

    set_auth_cookies(response, access_token, refresh_token)
    return user
