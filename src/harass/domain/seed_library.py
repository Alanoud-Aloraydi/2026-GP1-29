"""Group linked linguistic variants while rejecting ambiguous base-case identities."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from harass.domain.errors import InvalidEvaluationCaseError
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.taxonomy import ArabicVariety, Axis


@dataclass(frozen=True)
class SeedGroup:
    """The available varieties of one human-defined request, not inferred paraphrases."""

    axis: Axis
    base_case_number: str
    cases: tuple[EvaluationCase, ...]

    @property
    def missing_varieties(self) -> frozenset[ArabicVariety]:
        """Expose incomplete groups without manufacturing translations."""
        return frozenset(ArabicVariety) - {case.identifier.variety for case in self.cases}


def group_seeds(cases: Sequence[EvaluationCase]) -> tuple[SeedGroup, ...]:
    """Validate and group base requests for paired sampling and prompt-clustered metrics."""
    groups: dict[tuple[Axis, str], list[EvaluationCase]] = defaultdict(list)
    for case in cases:
        groups[(case.axis, case.identifier.base_case_number)].append(case)
    result = []
    for (axis, number), members in sorted(groups.items()):
        classifications = {
            (
                case.identifier.subject_domain,
                case.identifier.risk_category,
                case.identifier.strategy,
                case.identifier.owasp_category,
            )
            for case in members
        }
        varieties = [case.identifier.variety for case in members]
        if len(classifications) != 1 or len(varieties) != len(set(varieties)):
            raise InvalidEvaluationCaseError(
                f"Base case {axis.value}-{number} has conflicting classifications "
                "or duplicate varieties."
            )
        result.append(SeedGroup(axis, number, tuple(members)))
    return tuple(result)
