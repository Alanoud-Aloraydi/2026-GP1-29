"""Tests for invariants of evaluation cases and converter chains."""

import pytest

from harass.domain.case_identifier import CaseIdentifier
from harass.domain.errors import InvalidEvaluationCaseError
from harass.domain.evaluation_case import EvaluationCase


@pytest.mark.parametrize(
    ("prompt_text", "objective"), [("  ", "objective"), ("prompt", "")]
)
def test_evaluation_case_requires_prompt_and_objective(
    prompt_text: str, objective: str
) -> None:
    """Blank text cannot be sent or judged."""
    with pytest.raises(InvalidEvaluationCaseError):
        EvaluationCase(
            identifier=CaseIdentifier.parse("OR-DIN-VIO-MSA-00001"),
            prompt_text=prompt_text,
            objective=objective,
        )
