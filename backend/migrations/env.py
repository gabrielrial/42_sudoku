"""Alembic environment.

The database URL comes from the application settings, so it is read from the
environment and never stored in alembic.ini.

``target_metadata`` is the models' metadata, so ``alembic revision
--autogenerate`` can diff it against the database. Autogenerate's output is a
draft: it is always reviewed by hand before it is committed.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

import app.database.models  # noqa: F401  (registers every table in Base.metadata)
from app.config import get_settings
from app.database.conf.alch_conf import Base, make_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # The application's engine settings, UTC included: a migration that reads
    # or fills a timestamp sees it as the application does.
    connectable = make_engine(get_settings().database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
