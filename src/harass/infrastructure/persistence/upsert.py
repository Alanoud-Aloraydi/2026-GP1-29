"""Build atomic inserts for PostgreSQL and SQLite."""

from sqlalchemy.dialects.postgresql import Insert as PostgreSQLInsert
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import Insert as SQLiteInsert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from harass.infrastructure.persistence.tables import Base


def insert_for(
    session: Session, model: type[Base]
) -> PostgreSQLInsert | SQLiteInsert:
    """Select supported dialect-specific conflict handling."""
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        return postgresql_insert(model)
    if dialect == "sqlite":
        return sqlite_insert(model)
    raise ValueError(f"Atomic storage does not support dialect {dialect}.")
