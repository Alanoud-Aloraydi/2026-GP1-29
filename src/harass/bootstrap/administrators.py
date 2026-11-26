"""Composition root of the administrator access command."""

import os
import sys

from harass.application.accounts.administrators import ManageAdministrators
from harass.bootstrap.accounts import blocked_passwords, password_security
from harass.bootstrap.database import database_sessions, load_environment
from harass.infrastructure.persistence.sqlalchemy_authentication import (
    SqlAlchemyAuthenticationStore,
)
from harass.infrastructure.settings import BackendSettings, SettingsError
from harass.interfaces.cli.administrator_command import run_administrator_command


def main() -> None:
    """Entry point of the ``harass-admin`` command."""
    load_environment()
    try:
        backend = BackendSettings.from_environment(os.environ)
    except SettingsError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
    with database_sessions(backend.database_url) as factory:
        administrators = ManageAdministrators(
            SqlAlchemyAuthenticationStore(factory), password_security(backend), blocked_passwords()
        )
        status = run_administrator_command(sys.argv[1:], administrators, sys.stdout)
    sys.exit(status)


if __name__ == "__main__":
    main()
