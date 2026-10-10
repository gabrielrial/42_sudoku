from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.conf.alch_conf import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    intra_id: Mapped[int] = mapped_column(unique=True)
    login: Mapped[str] = mapped_column(unique=True)
    campus_id: Mapped[int]
    campus_name: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
