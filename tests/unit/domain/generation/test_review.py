"""Tests for the form reviewer's verdict record."""

from harass.domain.generation.review import CHECKS, CONTENT_CHECKS, Review


def test_variety_is_judged_apart_from_the_content_checks() -> None:
    """Verify the draft checks are every check but the variety."""
    assert "VARIETY" in CHECKS
    assert "VARIETY" not in CONTENT_CHECKS
    assert len(CONTENT_CHECKS) == len(CHECKS) - 1


def test_a_prompt_passes_only_when_every_check_says_yes() -> None:
    """Verify one failed check fails the whole review."""
    passing = Review({check: (True, "fine") for check in CHECKS})
    failing = Review({**passing.verdicts, "FACTS": (False, "invented a date")})
    assert passing.passed
    assert not failing.passed
    assert failing.score(CONTENT_CHECKS) == len(CONTENT_CHECKS) - 1


def test_a_missing_check_counts_as_failed_and_leaves_the_review_unobtained() -> None:
    """Verify an empty review fails and reports that nothing was read."""
    assert not Review().obtained
    assert not Review().passed
    assert Review().score(CHECKS) == 0
    assert Review({"DOMAIN": (True, "medicine")}).obtained


def test_notes_keep_the_verdict_and_its_reason_on_one_line() -> None:
    """Verify each verdict is flattened for storage."""
    review = Review({"DOMAIN": (True, "medicine"), "RISK": (False, "no alarming word")})
    assert review.notes == {"DOMAIN": "yes medicine", "RISK": "no no alarming word"}
