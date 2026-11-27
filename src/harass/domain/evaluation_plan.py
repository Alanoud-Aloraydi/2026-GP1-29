"""Select the paired dataset cases an evaluation sends."""

import random
from collections import defaultdict
from dataclasses import dataclass

from harass.domain.errors import InvalidEvaluationPlanError
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.taxonomy import Axis, SubjectDomain


@dataclass(frozen=True)
class EvaluationPlan:
    """The selected dataset cases, each sent once as written."""

    cases: tuple[EvaluationCase, ...]

    def __post_init__(self) -> None:
        """Reject plans that would send nothing."""
        if not self.cases:
            raise InvalidEvaluationPlanError("An evaluation plan requires at least one case.")


def sample_base_cases(
    cases: list[EvaluationCase], *, max_base_cases_per_axis: int | None, random_seed: int
) -> list[EvaluationCase]:
    """Sample base cases per axis while retaining paired varieties.

    Keep up to the given number of base cases per axis, with every variety of
    each kept case.

    Sampling whole base cases keeps comparisons across varieties paired on
    identical content. Base cases are allocated to subject domains in
    proportion to their share of the axis (largest-remainder method), so the
    sample preserves the domain composition.
    """
    if max_base_cases_per_axis is None:
        return list(cases)
    if max_base_cases_per_axis < 1:
        raise InvalidEvaluationPlanError("The number of base cases per axis must be positive.")
    generator = random.Random(random_seed)
    kept_keys: set[tuple[Axis, str]] = set()
    for axis in Axis:
        domain_by_base_case: dict[str, SubjectDomain] = {
            case.identifier.base_case_number: case.identifier.subject_domain
            for case in cases
            if case.axis is axis
        }
        if len(domain_by_base_case) <= max_base_cases_per_axis:
            kept_keys.update((axis, number) for number in domain_by_base_case)
            continue
        base_cases_by_domain: dict[SubjectDomain, list[str]] = defaultdict(list)
        for number, domain in sorted(domain_by_base_case.items()):
            base_cases_by_domain[domain].append(number)
        allocation = _allocate_proportionally(
            {domain: len(numbers) for domain, numbers in base_cases_by_domain.items()},
            max_base_cases_per_axis,
        )
        for domain, numbers in sorted(base_cases_by_domain.items()):
            chosen = generator.sample(numbers, allocation[domain])
            kept_keys.update((axis, number) for number in chosen)
    return [case for case in cases if (case.axis, case.identifier.base_case_number) in kept_keys]


def _allocate_proportionally(
    sizes: dict[SubjectDomain, int], total: int
) -> dict[SubjectDomain, int]:
    """Allocate stratum samples using the largest-remainder method."""
    population = sum(sizes.values())
    quotas = {domain: total * size / population for domain, size in sizes.items()}
    allocation = {domain: int(quota) for domain, quota in quotas.items()}
    unallocated = total - sum(allocation.values())
    largest_remainders_first = sorted(
        quotas, key=lambda domain: (-(quotas[domain] - allocation[domain]), domain.value)
    )
    for domain in largest_remainders_first[:unallocated]:
        allocation[domain] += 1
    return allocation
