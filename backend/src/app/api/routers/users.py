from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.cookies import clear_auth_cookies
from app.api.dependencies import get_current_user
from app.database.conf.dependencies import get_db
from app.database.models.users import User
from app.database.schema.user import UserPublic
from app.services.users import delete_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserPublic)
def read_me(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    return current_user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """The caller's account and everything of theirs, for good (D30)."""
    delete_user(db, current_user)
    clear_auth_cookies(response)
