from app.database.conf.alch_conf import Base
from sqlalchemy import CheckConstraint, String,Column, DateTime, ForeignKey, Integer, func

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
