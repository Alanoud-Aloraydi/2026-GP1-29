"""Tests for evaluation plans and base-case sampling."""

import pytest

from harass.domain.case_identifier import CaseIdentifier
from harass.domain.errors import InvalidEvaluationPlanError
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.evaluation_plan import EvaluationPlan, sample_base_cases
from harass.domain.prompt_variant import VariantSelection
from harass.domain.taxonomy import Axis, SubjectDomain


def case(identifier: str) -> EvaluationCase:
    """Return a case with placeholder text."""
    return EvaluationCase(
        identifier=CaseIdentifier.parse(identifier),
        prompt_text="p",
        objective="o",
    )


def over_refusal_cases(
    domain: str, base_numbers: range
) -> list[EvaluationCase]:
    """Return the MSA and Najdi versions of each base case in one domain."""
    return [
        case(f"OR-{domain}-VIO-{variety}-{digit}{number:04d}")
        for number in base_numbers
        for variety, digit in (("MSA", 0), ("NAJ", 1))
    ]


def test_plan_requires_cases_and_something_to_send() -> None:
    """An empty plan, or one without chains and baseline, is rejected."""
    with pytest.raises(InvalidEvaluationPlanError):
        EvaluationPlan(cases=())
    with pytest.raises(InvalidEvaluationPlanError):
        EvaluationPlan(
            cases=(case("OR-DIN-VIO-MSA-00001"),),
            include_baseline=False,
            variant_selection=VariantSelection((), ()),
        )


def test_without_a_limit_every_case_is_kept() -> None:
    """No limit means no sampling."""
    cases = over_refusal_cases("DIN", range(1, 4))

    assert (
        sample_base_cases(cases, max_base_cases_per_axis=None, random_seed=0)
        == cases
    )


def test_sampling_keeps_every_variety_and_preserves_domain_shares() -> None:
    """Verify sampling keeps every variety and preserves domain shares."""
    cases = over_refusal_cases("DIN", range(1, 7)) + over_refusal_cases(
        "TBB", range(7, 10)
    )

    sample = sample_base_cases(cases, max_base_cases_per_axis=3, random_seed=1)

    base_cases = {
        (item.identifier.subject_domain, item.identifier.base_case_number)
        for item in sample
    }
    domains = [domain for domain, _ in base_cases]
    assert domains.count(SubjectDomain("DIN")) == 2
    assert domains.count(SubjectDomain("TBB")) == 1
    assert len(sample) == 2 * len(base_cases)


def test_sampling_is_reproducible_and_applies_per_axis() -> None:
    """Verify sampling is reproducible and applies per axis."""
    cases = over_refusal_cases("DIN", range(1, 6)) + [
        case(f"AT-HSB-CRM-DIR-LLM01-MSA-0000{number}")
        for number in range(1, 6)
    ]

    first = sample_base_cases(cases, max_base_cases_per_axis=2, random_seed=7)
    second = sample_base_cases(cases, max_base_cases_per_axis=2, random_seed=7)

    assert first == second
    assert sum(item.axis is Axis.ADVERSARIAL for item in first) == 2
    assert sum(item.axis is Axis.OVER_REFUSAL for item in first) == 4


def test_non_positive_limit_is_rejected() -> None:
    """A limit below one is a configuration error."""
    with pytest.raises(InvalidEvaluationPlanError):
        sample_base_cases(
            [case("OR-DIN-VIO-MSA-00001")],
            max_base_cases_per_axis=0,
            random_seed=0,
        )
