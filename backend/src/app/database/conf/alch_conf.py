from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_settings

_settings = get_settings()

engine = create_engine(_settings.database_url, pool_pre_ping=True, future=True)

SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

Base = declarative_base()
