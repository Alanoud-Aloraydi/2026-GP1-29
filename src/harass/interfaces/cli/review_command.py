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
    """Prepare blind human labels or analyze explicitly labelled review files."""
    parser = argparse.ArgumentParser(prog="harass-review")
    commands = parser.add_subparsers(dest="action", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--report", type=Path, required=True)
    prepare_parser.add_argument("--output", type=Path, required=True)
    leak_prepare_parser = commands.add_parser("prepare-leak")
    leak_prepare_parser.add_argument("--report", type=Path, required=True)
    leak_prepare_parser.add_argument("--output", type=Path, required=True)
    score_parser = commands.add_parser("agreement")
    score_parser.add_argument("--report", type=Path, required=True)
    score_parser.add_argument("--labels", type=Path, required=True)
    leak_parser = commands.add_parser("calibrate-leak")
    leak_parser.add_argument("--labels", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        if arguments.action == "prepare":
            prepare(arguments.report, arguments.output)
            print("Blind review CSV created; human categories are blank.", file=output)
        elif arguments.action == "prepare-leak":
            prepare_leak(arguments.report, arguments.output)
            print("Leak review CSV created; labels and split assignments are blank.", file=output)
        else:
            result = (
                score(arguments.report, arguments.labels)
                if arguments.action == "agreement"
                else calibrate(arguments.labels)
            )
            print(json.dumps(result, ensure_ascii=False, indent=2), file=output)
    except (OSError, DomainError, json.JSONDecodeError) as error:
        print(f"Review error: {error}", file=output)
        return 1
    return 0
