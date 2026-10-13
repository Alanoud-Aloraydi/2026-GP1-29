"""Tests for inter-rater agreement."""

import pytest

from harass.domain.agreement import cohen_kappa


def test_perfect_agreement_is_one() -> None:
    """Identical labels with more than one category give kappa 1."""
    assert cohen_kappa(["FUL", "REF", "PRF"], ["FUL", "REF", "PRF"]) == pytest.approx(1.0)


def test_kappa_matches_a_hand_computed_value() -> None:
    """Observed 0.75, chance 0.5 (two balanced labels) gives (0.75 - 0.5) / 0.5 = 0.5."""
    first = ["FUL", "FUL", "REF", "REF"]
    second = ["FUL", "REF", "REF", "REF"]
    # Chance: P(FUL) = 0.5 * 0.25, P(REF) = 0.5 * 0.75, sum 0.5.

    assert cohen_kappa(first, second) == pytest.approx(0.5)


def test_undefined_cases_return_none() -> None:
    """No pairs, or a single label used by both raters, leave kappa undefined."""
    assert cohen_kappa([], []) is None
    assert cohen_kappa(["FUL", "FUL"], ["FUL", "FUL"]) is None


def test_unequal_lengths_are_rejected() -> None:
    """Labels must be paired."""
    with pytest.raises(ValueError, match="same number"):
        cohen_kappa(["FUL"], [])
