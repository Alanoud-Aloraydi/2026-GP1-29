"""Criteria for selecting evaluation cases."""

from dataclasses import dataclass

from harass.domain.errors import InvalidCaseSelectionError
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.taxonomy import (
    ArabicVariety,
    Axis,
    BypassStrategy,
    RiskCategory,
    SubjectDomain,
)


@dataclass(frozen=True)
class CaseSelection:
    """Filter cases; empty criteria impose no restriction.

    Strategy criteria apply to adversarial cases only, because over-refusal
    cases carry no bypass strategy. An adversarial case matches when its
    strategy is one of those selected.
    """

    axis: Axis | None = None
    subject_domains: frozenset[SubjectDomain] = frozenset()
    risk_categories: frozenset[RiskCategory] = frozenset()
    varieties: frozenset[ArabicVariety] = frozenset()
    strategies: frozenset[BypassStrategy] = frozenset()

    def __post_init__(self) -> None:
        """Reject strategy filters restricted to over-refusal cases."""
        if self.axis is Axis.OVER_REFUSAL and self.strategies:
            raise InvalidCaseSelectionError(
                "Bypass strategies cannot be selected for over-refusal cases."
            )

    def matches(self, case: EvaluationCase) -> bool:
        """Return whether the case satisfies every criterion."""
        identifier = case.identifier
        if self.axis is not None and identifier.axis is not self.axis:
            return False
        if (
            self.subject_domains
            and identifier.subject_domain not in self.subject_domains
        ):
            return False
        if (
            self.risk_categories
            and identifier.risk_category not in self.risk_categories
        ):
            return False
        if self.varieties and identifier.variety not in self.varieties:
            return False
        return not (
            self.strategies
            and identifier.axis is Axis.ADVERSARIAL
            and identifier.strategy not in self.strategies
        )
