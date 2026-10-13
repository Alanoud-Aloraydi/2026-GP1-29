"""Tests for case selection criteria."""

import pytest

from harass.domain.case_identifier import CaseIdentifier
from harass.domain.case_selection import CaseSelection
from harass.domain.errors import InvalidCaseSelectionError
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.taxonomy import (
    ArabicVariety,
    Axis,
    BypassStrategy,
    RiskCategory,
    SubjectDomain,
)

OVER_REFUSAL_CASE = EvaluationCase(
    identifier=CaseIdentifier.parse("OR-DIN-VIO-MSA-00001"),
    prompt_text="prompt",
    objective="prompt",
)
ADVERSARIAL_CASE = EvaluationCase(
    identifier=CaseIdentifier.parse("AT-SIY-MIS-ROL-LLM07-HIJ-20002"),
    prompt_text="prompt",
    objective="objective",
)


def test_empty_selection_matches_every_case() -> None:
    """No criterion means no restriction."""
    selection = CaseSelection()

    assert selection.matches(OVER_REFUSAL_CASE)
    assert selection.matches(ADVERSARIAL_CASE)


@pytest.mark.parametrize(
    ("selection", "expected_over_refusal", "expected_adversarial"),
    [
        (CaseSelection(axis=Axis.ADVERSARIAL), False, True),
        (CaseSelection(subject_domains=frozenset({SubjectDomain.RELIGION_AND_LAW})), True, False),
        (CaseSelection(risk_categories=frozenset({RiskCategory.MISINFORMATION})), False, True),
        (CaseSelection(varieties=frozenset({ArabicVariety.MODERN_STANDARD})), True, False),
    ],
)
def test_each_criterion_filters_on_its_dimension(
    selection: CaseSelection, expected_over_refusal: bool, expected_adversarial: bool
) -> None:
    """A case matches only when its code is among the selected codes."""
    assert selection.matches(OVER_REFUSAL_CASE) is expected_over_refusal
    assert selection.matches(ADVERSARIAL_CASE) is expected_adversarial


def test_strategy_matches_when_the_case_strategy_is_selected() -> None:
    """An adversarial case matches when its strategy is among those selected."""
    assert CaseSelection(strategies=frozenset({BypassStrategy.ROLE_FRAMING})).matches(
        ADVERSARIAL_CASE
    )
    assert not CaseSelection(strategies=frozenset({BypassStrategy.OBFUSCATION})).matches(
        ADVERSARIAL_CASE
    )


def test_strategy_criterion_leaves_over_refusal_cases_unfiltered() -> None:
    """Over-refusal cases carry no strategy, so strategy criteria do not exclude them."""
    selection = CaseSelection(strategies=frozenset({BypassStrategy.OBFUSCATION}))

    assert selection.matches(OVER_REFUSAL_CASE)


def test_rejects_strategy_criterion_on_over_refusal_axis() -> None:
    """Selecting strategies for over-refusal cases is contradictory."""
    with pytest.raises(InvalidCaseSelectionError):
        CaseSelection(
            axis=Axis.OVER_REFUSAL, strategies=frozenset({BypassStrategy.DIRECT_REQUEST})
        )
