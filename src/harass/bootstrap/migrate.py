"""Apply explicit database migrations as a standalone deployment step."""

from alembic import command

from harass.infrastructure.persistence.schema import migration_config


def main() -> None:
    """Upgrade the configured database before API and worker admission."""
    command.upgrade(migration_config(), "head")


if __name__ == "__main__":
    main()
