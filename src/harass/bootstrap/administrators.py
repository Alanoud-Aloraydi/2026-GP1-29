"""Composition root of the administrator access command."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from harass.application.accounts.administrators import ManageAdministrators
from harass.application.accounts.password_policy import PasswordPolicy
from harass.infrastructure.persistence.schema import require_current_schema
from harass.infrastructure.persistence.sqlalchemy_authentication import (
    SqlAlchemyAuthenticationStore,
)
from harass.infrastructure.security.jwt_authentication import (
    JwtAuthenticationSecurity,
)
from harass.infrastructure.security.password_blocklist import password_hashes
from harass.infrastructure.settings import BackendSettings, SettingsError
from harass.interfaces.cli.administrator_command import (
    run_administrator_command,
)

ENVIRONMENT_FILE = Path(".env")


def main() -> None:
    """Entry point of the ``harass-admin`` command."""
    load_dotenv(ENVIRONMENT_FILE)
    try:
        backend = BackendSettings.from_environment(os.environ)
    except SettingsError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
    engine = create_engine(
        backend.database_url,
        connect_args={"connect_timeout": 10},
        pool_pre_ping=True,
    )
    try:
        require_current_schema(engine)
        administrators = ManageAdministrators(
            SqlAlchemyAuthenticationStore(sessionmaker(engine)),
            JwtAuthenticationSecurity(
                backend.jwt_secret,
                previous_keys=backend.previous_jwt_secrets,
            ),
            PasswordPolicy(
                password_hashes(
                    os.environ.get("HARASS_PASSWORD_BLOCKLIST_PATH")
                )
            ),
        )
        status = run_administrator_command(
            sys.argv[1:], administrators, sys.stdout
        )
    finally:
        engine.dispose()
    sys.exit(status)


if __name__ == "__main__":
    main()
