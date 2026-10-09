import pytest
from sqlalchemy.orm import Session

from app.database.models.users import User

@pytest.fixture
def ana(db: Session) -> User:
    """One saved user, for tests that need a signed-in somebody."""
    user = User(username="ana", password_hash="not-a-real-hash")
    db.add(user)
    db.commit()
    return user
