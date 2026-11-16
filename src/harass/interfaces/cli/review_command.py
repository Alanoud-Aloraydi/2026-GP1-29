"""Review commands with file operations injected by the composition root."""

import argparse
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TextIO

from harass.domain.errors import DomainError

type PrepareReview = Callable[[Path, Path], None]
type ScoreReview = Callable[[Path, Path], dict[str, Any]]
type CalibrateLeak = Callable[[Path], dict[str, Any]]


def run_review_command(
    argv: Sequence[str],
    prepare: PrepareReview,
    prepare_leak: PrepareReview,
    score: ScoreReview,
    calibrate: CalibrateLeak,
    output: TextIO,
) -> int:
    """Prepare blind labels or analyze completed review files."""
    arguments = _parser().parse_args(argv)
    try:
        if arguments.action == "prepare":
            prepare(arguments.report, arguments.output)
            message = "Blind review CSV created; human categories are blank."
        elif arguments.action == "prepare-leak":
            prepare_leak(arguments.report, arguments.output)
            message = (
                "Leak review CSV created; labels and split assignments "
                "are blank."
            )
        else:
            result = (
                score(arguments.report, arguments.labels)
                if arguments.action == "agreement"
                else calibrate(arguments.labels)
            )
            message = json.dumps(result, ensure_ascii=False, indent=2)
    except (OSError, DomainError, json.JSONDecodeError) as error:
        print(f"Review error: {error}", file=output)
        return 1
    print(message, file=output)
    return 0


def _parser() -> argparse.ArgumentParser:
    """Describe each review subcommand and the files it reads or writes."""
    parser = argparse.ArgumentParser(prog="harass-review")
    commands = parser.add_subparsers(dest="action", required=True)
    files = {
        "prepare": ("--report", "--output"),
        "prepare-leak": ("--report", "--output"),
        "agreement": ("--report", "--labels"),
        "calibrate-leak": ("--labels",),
    }
    for action, options in files.items():
        command = commands.add_parser(action)
        for option in options:
            command.add_argument(option, type=Path, required=True)
    return parser
