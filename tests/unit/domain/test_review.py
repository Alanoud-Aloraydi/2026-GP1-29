"""Human-label coverage and calibration checks without fabricated human judgments."""

from dataclasses import replace

import pytest

from harass.domain.review import (
    HumanCategory,
    InvalidReviewDataError,
    LeakObservation,
    ReviewCase,
    calibrate_leak,
    review_agreement,
)
from harass.domain.taxonomy import ResponseCategory


def test_agreement_exposes_missing_labels_and_known_confusion() -> None:
    """Only paired categories contribute, while unfinished review remains visible."""
    cases = [
        ReviewCase("one", "baseline", ResponseCategory.FULL_COMPLIANCE, "", "", ""),
        ReviewCase("two", "baseline", ResponseCategory.FULL_REFUSAL, "", "", ""),
        ReviewCase("three", "baseline", None, "", "", ""),
    ]
    labels = [
        HumanCategory("one", "baseline", ResponseCategory.FULL_COMPLIANCE),
        HumanCategory("two", "baseline", ResponseCategory.FULL_COMPLIANCE),
        HumanCategory("three", "baseline", None),
    ]
    result = review_agreement(cases, labels)
    assert result["paired_labels"] == 2
    assert result["missing_human_labels"] == 1
    assert result["agreement_rate"] == 0.5
    assert result["confusion_matrix_human_rows_judge_columns"]["FUL"]["REF"] == 1


def test_empty_human_review_has_no_reliability_estimate() -> None:
    """An empty human annotation set cannot establish judge reliability."""
    result = review_agreement(
        [ReviewCase("one", "baseline", ResponseCategory.UNCLEAR, "", "", "")], []
    )
    assert result["cohen_kappa"] is None
    assert result["missing_human_labels"] == 1


def test_calibration_uses_held_out_references_and_declares_synthetic_scope() -> None:
    """Synthetic fixtures exercise tooling but do not establish human validation."""
    calibration = LeakObservation(
        "سجل خاص alpha داخلي", "alpha", "alpha", True, "calibration", "synthetic_oracle"
    )
    evaluation = LeakObservation(
        "سياق محمي beta مستقل", "beta", "beta", True, "evaluation", "synthetic_oracle"
    )
    result = calibrate_leak(
        [
            calibration,
            replace(calibration, response="إجابة عامة", leaked=False),
            evaluation,
            replace(evaluation, response="لا معلومات", leaked=False),
        ]
    )
    assert result["held_out_evaluation"]["true_positive"] == 1
    assert result["held_out_evaluation"]["true_negative"] == 1
    assert result["settings_changed"] is False
    assert result["label_scope"] == "synthetic_or_mixed"
    assert len(result["threshold_sensitivity"]) == 20


def test_calibration_rejects_reference_leakage_between_splits() -> None:
    """Duplicating a protected reference across train/test invalidates held-out evidence."""
    row = LeakObservation("نص محمي alpha", "alpha", "alpha", True, "calibration", "human")
    with pytest.raises(InvalidReviewDataError, match="both splits"):
        calibrate_leak([row, replace(row, split="evaluation")])


def test_unknown_annotation_identity_is_rejected() -> None:
    """A mismatched CSV cannot silently label a different source outcome."""
    with pytest.raises(InvalidReviewDataError):
        review_agreement([], [HumanCategory("absent", "baseline", ResponseCategory.FULL_REFUSAL)])
