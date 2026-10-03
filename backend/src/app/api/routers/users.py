from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.cookies import set_auth_cookies
from app.api.dependencies import get_current_user
from app.api.rate_limits import limit_login_attempts
from app.database.conf.dependencies import get_db
from app.database.models.users import User
from app.database.schema.user import PASSWORD_MAX_LENGTH, UserCreate, UserPublic
from app.services.auth import create_access_token
from app.services.refresh_token import issue_refresh_token
from app.utils.security import DUMMY_HASH, hash_password, verify_password

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserPublic)
def read_me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user


@router.post("/login", response_model=UserPublic, dependencies=[Depends(limit_login_attempts)])
def login(
    response: Response,
    form: Annotated[OAuth2PasswordRequestForm, Depends()], 
    db: Annotated[Session, Depends(get_db)]):
    user = db.query(User).filter(User.username == form.username.lower()).first()

    if len(form.password) > PASSWORD_MAX_LENGTH:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    password = verify_password(form.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access_token = create_access_token(user)
    refresh_token = issue_refresh_token(db, user.id)
    db.commit()

    set_auth_cookies(response, access_token, refresh_token)
    return user


@router.post("/signup", status_code=status.HTTP_201_CREATED, response_model=UserPublic)
def signup(user: UserCreate, db: Annotated[Session, Depends(get_db)]):
    db_user = db.query(User).filter(User.username == user.username).first()

    if db_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")

    new_user = User(username=user.username, password_hash=hash_password(user.password))
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user
