"""Selection of paired cases, eligible recipes and execution policy for one run."""

import random
from collections import defaultdict
from dataclasses import dataclass, field

from harass.domain.errors import InvalidEvaluationPlanError
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.prompt_variant import AdaptiveSettings, VariantSelection
from harass.domain.taxonomy import Axis, SubjectDomain


@dataclass(frozen=True)
class EvaluationPlan:
    """Selected cases and recipe filters; baseline sends the original request."""

    cases: tuple[EvaluationCase, ...]
    include_baseline: bool = True
    variant_selection: VariantSelection = field(default_factory=VariantSelection)
    adaptive_settings: AdaptiveSettings = field(default_factory=AdaptiveSettings)

    def __post_init__(self) -> None:
        """Reject plans that would send nothing."""
        if not self.cases:
            raise InvalidEvaluationPlanError("An evaluation plan requires at least one case.")
        if not self.include_baseline and self.variant_selection == VariantSelection((), ()):
            raise InvalidEvaluationPlanError(
                "An evaluation plan requires eligible variants or the baseline."
            )


def sample_base_cases(
    cases: list[EvaluationCase], *, max_base_cases_per_axis: int | None, random_seed: int
) -> list[EvaluationCase]:
    """Keep up to the given number of base cases per axis, with every variety of each kept case.

    Sampling whole base cases keeps comparisons across varieties paired on identical content.
    Base cases are allocated to subject domains in proportion to their share of the axis
    (largest-remainder method), so the sample preserves the domain composition.
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
    """Split ``total`` across strata proportionally to their sizes by largest remainder."""
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
