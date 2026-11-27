"""Publish judge benchmark report files with the storage injected."""

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO

from harass.application.errors import ApplicationError

type PublishReports = Callable[[Path], list[str]]


def run_report_command(argv: Sequence[str], publish: PublishReports, output: TextIO) -> int:
    """Publish one report file and print the stored identifiers."""
    parser = argparse.ArgumentParser(
        prog="harass-reports", description="Publish judge benchmark reports for administrators."
    )
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("publish", help="store a report file").add_argument("report", type=Path)
    arguments = parser.parse_args(argv)
    try:
        identifiers = publish(arguments.report)
    except (OSError, ValueError, ApplicationError) as error:
        print(f"Report error: {error}", file=output)
        return 1
    for identifier in identifiers:
        print(f"Published judge report {identifier}.", file=output)
    return 0
