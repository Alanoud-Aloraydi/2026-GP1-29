"""Tests for review command."""

import io
from pathlib import Path

from harass.domain.review import InvalidReviewDataError
from harass.interfaces.cli.review_command import run_review_command


def test_review_cli_preserves_blind_and_unfinished_labels() -> None:
    """Verify review cli preserves blind and unfinished labels."""
    prepared = []

    def prepare(source: Path, destination: Path) -> None:
        prepared.append((source, destination))

    output = io.StringIO()
    assert (
        run_review_command(
            ["prepare", "--report", "report.json", "--output", "review.csv"],
            prepare,
            prepare,
            lambda report, labels: {"paired_labels": 0},
            lambda labels: {},
            output,
        )
        == 0
    )
    assert prepared == [(Path("report.json"), Path("review.csv"))]
    assert "human categories are blank" in output.getvalue()


def test_review_cli_rejects_missing_calibration_ground_truth() -> None:
    """Verify review cli rejects missing calibration ground truth."""

    def calibrate(source: Path) -> dict[str, object]:
        raise InvalidReviewDataError("Both label classes are required.")

    output = io.StringIO()
    assert (
        run_review_command(
            ["calibrate-leak", "--labels", "empty.csv"],
            lambda source, destination: None,
            lambda source, destination: None,
            lambda report, labels: {},
            calibrate,
            output,
        )
        == 1
    )
    assert "Both label classes" in output.getvalue()
