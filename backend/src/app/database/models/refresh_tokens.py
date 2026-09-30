from sqlalchemy import UUID, Column, DateTime, ForeignKey, Integer, String, func

from app.database.conf.alch_conf import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    token_hash = Column(String, unique=True, nullable=False)

    family_id = Column(UUID, index=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    used_at = Column(DateTime(timezone=True), nullable=True)
