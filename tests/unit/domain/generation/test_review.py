"""Tests for the form reviewer's verdict record."""

from harass.domain.generation.review import OVER_REFUSAL_CHECKS, OVER_REFUSAL_CONTENT_CHECKS, Review


def test_variety_is_judged_apart_from_the_content_checks() -> None:
    """Verify the draft checks are every check but the variety."""
    assert "VARIETY" in OVER_REFUSAL_CHECKS
    assert "VARIETY" not in OVER_REFUSAL_CONTENT_CHECKS
    assert len(OVER_REFUSAL_CONTENT_CHECKS) == len(OVER_REFUSAL_CHECKS) - 1


def test_a_prompt_passes_only_when_every_check_says_yes() -> None:
    """Verify one failed check fails the whole review."""
    passing = Review(OVER_REFUSAL_CHECKS, {check: (True, "fine") for check in OVER_REFUSAL_CHECKS})
    failing = Review(OVER_REFUSAL_CHECKS, {**passing.verdicts, "FACTS": (False, "invented a date")})
    assert passing.passed
    assert not failing.passed
    assert failing.score(OVER_REFUSAL_CONTENT_CHECKS) == len(OVER_REFUSAL_CONTENT_CHECKS) - 1


def test_a_missing_check_counts_as_failed_and_leaves_the_review_unobtained() -> None:
    """Verify an empty review fails and reports that nothing was read."""
    assert not Review(OVER_REFUSAL_CHECKS).obtained
    assert not Review(OVER_REFUSAL_CHECKS).passed
    assert Review(OVER_REFUSAL_CHECKS).score(OVER_REFUSAL_CHECKS) == 0
    assert Review(OVER_REFUSAL_CHECKS, {"DOMAIN": (True, "medicine")}).obtained


def test_notes_keep_the_verdict_and_its_reason_on_one_line() -> None:
    """Verify each verdict is flattened for storage."""
    review = Review(
        OVER_REFUSAL_CHECKS, {"DOMAIN": (True, "medicine"), "RISK": (False, "no alarming word")}
    )
    assert review.notes == {"DOMAIN": "yes medicine", "RISK": "no no alarming word"}
