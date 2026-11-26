"""Tests for the judge report publish command."""

import io
from pathlib import Path

import pytest

from harass.application.errors import InvalidBenchmarkReportError
from harass.interfaces.cli.report_command import run_report_command


def test_publishing_prints_every_stored_identifier() -> None:
    """A file with several reports prints one identifier per stored report."""
    seen: list[Path] = []

    def publish(path: Path) -> list[str]:
        """Record the request and pretend two reports were stored."""
        seen.append(path)
        return ["first-id", "second-id"]

    output = io.StringIO()

    status = run_report_command(["publish", "reports.json"], publish, output)

    assert status == 0
    assert seen == [Path("reports.json")]
    assert "first-id" in output.getvalue()
    assert "second-id" in output.getvalue()


def test_an_invalid_report_fails_with_a_message() -> None:
    """A malformed report exits with an error instead of a traceback."""

    def publish(path: Path) -> list[str]:
        """Reject the report the way the service does."""
        raise InvalidBenchmarkReportError("The report has no judge section.")

    output = io.StringIO()

    status = run_report_command(["publish", "report.json"], publish, output)

    assert status == 1
    assert "no judge section" in output.getvalue()


def test_a_missing_file_argument_is_refused() -> None:
    """The command needs the report file to publish."""
    with pytest.raises(SystemExit):
        run_report_command(["publish"], lambda path: [], io.StringIO())
