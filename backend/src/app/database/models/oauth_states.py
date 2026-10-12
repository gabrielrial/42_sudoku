from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database.conf.alch_conf import Base


class OAuthState(Base):
    __tablename__ = "oauth_states"

    state: Mapped[str] = mapped_column(primary_key=True)
    code_verifier: Mapped[str]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
