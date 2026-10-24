"""Compose blind-review preparation and calibration commands."""

import sys

from harass.infrastructure.reporting.review_files import (
    prepare_leak_review,
    prepare_review,
    score_leak_calibration,
    score_review,
)
from harass.interfaces.cli.review_command import run_review_command


def main() -> None:
    """Compose review commands without loading model credentials."""
    sys.exit(
        run_review_command(
            sys.argv[1:],
            prepare_review,
            prepare_leak_review,
            score_review,
            score_leak_calibration,
            sys.stdout,
        )
    )


if __name__ == "__main__":
    main()
