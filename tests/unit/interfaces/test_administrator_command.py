"""Tests for the administrator access command."""

import io
from collections.abc import Callable
from dataclasses import replace
from typing import cast
from unittest.mock import Mock

import pytest

from harass.application.accounts.administrators import ManageAdministrators
from harass.application.accounts.errors import UnknownAccountError
from harass.domain.authentication import User, UserRole
from harass.interfaces.cli.administrator_command import run_administrator_command

USER = User("id-1", "Member", "member@example.test", "hash")


def service(**behaviour: object) -> ManageAdministrators:
    """Build a stand-in for the administrator service."""
    return cast(ManageAdministrators, Mock(**behaviour))


def test_grant_reports_the_new_administrator() -> None:
    """A successful grant names the account and exits cleanly."""
    administrators = service(**{"grant.return_value": replace(USER, role=UserRole.ADMINISTRATOR)})
    output = io.StringIO()

    status = run_administrator_command(
        ["grant", "--email", "member@example.test"], administrators, output
    )

    assert status == 0
    assert "member@example.test is now an administrator" in output.getvalue()


def test_revoke_reports_the_plain_user() -> None:
    """A revocation names the account and exits cleanly."""
    administrators = service(**{"revoke.return_value": USER})
    output = io.StringIO()

    status = run_administrator_command(
        ["revoke", "--email", "member@example.test"], administrators, output
    )

    assert status == 0
    assert "is now a plain user" in output.getvalue()


def test_unknown_account_is_an_error() -> None:
    """A missing account prints an error and exits with failure."""
    administrators = service(
        **{"grant.side_effect": UnknownAccountError("No account has this email.")}
    )
    output = io.StringIO()

    status = run_administrator_command(
        ["grant", "--email", "x@example.test"], administrators, output
    )

    assert status == 1
    assert "Administrator error: No account has this email." in (output.getvalue())


def test_email_is_required() -> None:
    """The command refuses to run without an email."""
    with pytest.raises(SystemExit) as stop:
        run_administrator_command(["grant"], service(), io.StringIO())

    assert stop.value.code == 2


def typing_secrets(*typed: str) -> Callable[[str], str]:
    """Return a prompt reader that answers with the typed secrets in turn."""
    answers = iter(typed)
    return lambda prompt: next(answers)


def test_reset_password_reads_the_secret_from_the_terminal() -> None:
    """The password reaches the service and never the output."""
    administrators = service(**{"reset_password.return_value": USER})
    output = io.StringIO()

    status = run_administrator_command(
        ["reset-password", "--email", "member@example.test"],
        administrators,
        output,
        typing_secrets("a-typed-secret-2026", "a-typed-secret-2026"),
    )

    assert status == 0
    reset = cast(Mock, administrators).reset_password
    reset.assert_called_once_with("member@example.test", "a-typed-secret-2026")
    assert "was reset and its sessions ended" in output.getvalue()
    assert "a-typed-secret-2026" not in output.getvalue()


def test_reset_password_stops_when_the_two_entries_differ() -> None:
    """A typing slip changes nothing."""
    administrators = service()
    output = io.StringIO()

    status = run_administrator_command(
        ["reset-password", "--email", "member@example.test"],
        administrators,
        output,
        typing_secrets("first-entry-2026-xx", "other-entry-2026-xx"),
    )

    assert status == 1
    assert "Passwords differ" in output.getvalue()
    assert not cast(Mock, administrators).reset_password.called
