import pytest
from sqlalchemy.orm import Session

from app.database.models.users import User
from app.utils.security import hash_password
from tests.api.helpers import PASSWORD


@pytest.fixture
def ana(db: Session) -> User:
    """A saved user whose password is ``helpers.PASSWORD``, so tests can log in."""
    user = User(username="ana", password_hash=hash_password(PASSWORD))
    db.add(user)
    db.commit()
    return user
