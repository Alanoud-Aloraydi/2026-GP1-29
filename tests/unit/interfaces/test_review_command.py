"""The review CLI routes commands through injected operations and exposes missing-data errors."""

import io
from pathlib import Path

from harass.domain.review import InvalidReviewDataError
from harass.interfaces.cli.review_command import run_review_command


def test_review_cli_preserves_blind_preparation_and_reports_unfinished_labels() -> None:
    """Preparing a review uses the requested paths and agreement reports no invented pairs."""
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
    """Missing review data return a failure status rather than a fabricated threshold."""

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
