"""Explicit schema readiness checks before production storage is used."""

from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine


def migration_config() -> Config:
    """Locate packaged migrations without embedding credentials."""
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).with_name("migrations"))
    )
    return config


def require_current_schema(engine: Engine) -> None:
    """Reject schemas that require an explicit migration."""
    heads = set(ScriptDirectory.from_config(migration_config()).get_heads())
    with engine.connect() as connection:
        current = set(
            MigrationContext.configure(connection).get_current_heads()
        )
    if current != heads:
        raise RuntimeError(
            "Database schema is not current; run alembic upgrade head first."
        )
