"""Composition root for blind review preparation and reliability/calibration analysis."""

import sys

from harass.infrastructure.reporting.review_files import (
    prepare_leak_review,
    prepare_review,
    score_leak_calibration,
    score_review,
)
from harass.interfaces.cli.review_command import run_review_command


def main() -> None:
    """Wire review file adapters into the command without loading model credentials."""
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
