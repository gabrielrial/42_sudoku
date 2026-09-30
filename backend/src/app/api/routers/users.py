from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database.conf.dependencies import get_db
from app.database.models.users import User
from app.database.schema.user import UserCreate, UserPublic
from app.services.auth import create_access_token
from app.utils.security import hash_password, verify_password, DUMMY_HASH
from app.api.cookies import set_auth_cookies
from app.services.refresh_token import issue_refresh_token

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/")
def get_users(db: Session = Depends(get_db)):
    return {"status": "ok"}


@router.post("/login", response_model=UserPublic)
def login(response: Response, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form.username).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    password = verify_password(form.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    
    access_token = create_access_token(user)
    refresh_token = issue_refresh_token(db,user.id)
    db.commit()

    set_auth_cookies(response , access_token, refresh_token)
    return user
    


@router.post("/signup", status_code=status.HTTP_201_CREATED, response_model=UserPublic)
def signup(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()

    if db_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")

    new_user = User(username=user.username, password_hash=hash_password(user.password))
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user
