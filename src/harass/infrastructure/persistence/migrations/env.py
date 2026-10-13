"""Alembic execution with credentials supplied by environment or an injected connection."""

import os
from pathlib import Path

from alembic import context
from dotenv import dotenv_values
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.pool import NullPool

from harass.infrastructure.persistence.tables import Base


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


injected = context.config.attributes.get("connection")
if injected is not None:
    _run(injected)
else:
    environment = {**dotenv_values(Path(".env")), **os.environ}
    url = environment.get("HARASS_DATABASE_URL")
    if not url:
        raise ValueError("HARASS_DATABASE_URL is required for database migrations.")
    if context.is_offline_mode():
        context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = create_engine(url, poolclass=NullPool)
        try:
            with engine.connect() as connection:
                _run(connection)
        finally:
            engine.dispose()
