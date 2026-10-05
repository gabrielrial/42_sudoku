import uuid
from datetime import datetime

from sqlalchemy import UUID, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.conf.alch_conf import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    token_hash: Mapped[str] = mapped_column(unique=True)

    family_id: Mapped[uuid.UUID] = mapped_column(UUID, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
