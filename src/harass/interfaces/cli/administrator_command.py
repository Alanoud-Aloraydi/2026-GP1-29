"""Administrator access commands with the service injected."""

import argparse
import getpass
from collections.abc import Callable, Sequence
from typing import TextIO

from harass.application.accounts.administrators import ManageAdministrators
from harass.application.errors import ApplicationError


def run_administrator_command(
    argv: Sequence[str],
    administrators: ManageAdministrators,
    output: TextIO,
    read_secret: Callable[[str], str] = getpass.getpass,
) -> int:
    """Grant or revoke administrator access, or reset a password.

    The new password is read from the terminal and never from the arguments,
    so it stays out of shell history and process listings.
    """
    parser = argparse.ArgumentParser(prog="harass-admin")
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("grant", "revoke"):
        commands.add_parser(action).add_argument("--email", required=True)
    commands.add_parser("reset-password").add_argument(
        "--email", required=True
    )
    arguments = parser.parse_args(argv)
    try:
        if arguments.action == "grant":
            user = administrators.grant(arguments.email)
            print(f"{user.email} is now an administrator.", file=output)
        elif arguments.action == "revoke":
            user = administrators.revoke(arguments.email)
            print(f"{user.email} is now a plain user.", file=output)
        else:
            password = read_secret("New password: ")
            if read_secret("Repeat the new password: ") != password:
                print("Administrator error: Passwords differ.", file=output)
                return 1
            user = administrators.reset_password(arguments.email, password)
            print(
                f"The password of {user.email} was reset "
                "and its sessions ended.",
                file=output,
            )
    except ApplicationError as error:
        print(f"Administrator error: {error}", file=output)
        return 1
    return 0
