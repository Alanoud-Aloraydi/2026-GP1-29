"""Define framework-independent prompt variants and recipe contracts."""

import re
from dataclasses import dataclass, field
from enum import StrEnum

from harass.domain.errors import InvalidEvaluationPlanError
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.taxonomy import (
    ArabicVariety,
    Axis,
    BypassStrategy,
    OwaspCategory,
    RiskCategory,
    SubjectDomain,
)


class EvaluationMode(StrEnum):
    """Whether eligible variants are enumerated or selected from feedback."""

    STATIC = "static"
    ADAPTIVE = "adaptive"


@dataclass(frozen=True)
class VariantSelection:
    """Filter recipes; None selects all and empty tuples select none."""

    template_names: tuple[str, ...] | None = None
    transform_names: tuple[str, ...] | None = None


@dataclass(frozen=True)
class PromptTemplate:
    """An authored shell containing exactly one unchanged seed placeholder."""

    name: str
    label: str
    text: str
    axis: Axis
    strategy: BypassStrategy | None
    varieties: frozenset[ArabicVariety]
    revision: str
    source: str
    review_status: str = "draft"
    subject_domains: frozenset[SubjectDomain] = field(
        default_factory=frozenset
    )
    risk_categories: frozenset[RiskCategory] = field(default_factory=frozenset)
    owasp_categories: frozenset[OwaspCategory] = field(
        default_factory=frozenset
    )

    def __post_init__(self) -> None:
        """Validate recipe completeness and axis assignments."""
        if (
            not re.fullmatch(r"[a-z][a-z0-9_]*", self.name)
            or self.name in {"baseline", "seed"}
            or not self.label.strip()
            or self.text.count("{seed}") != 1
        ):
            raise InvalidEvaluationPlanError(
                "Templates require a name, label and one {seed}."
            )
        if not self.varieties or not self.revision or not self.source:
            raise InvalidEvaluationPlanError(
                f"Template {self.name} lacks provenance or varieties."
            )
        if (self.axis is Axis.ADVERSARIAL) != (self.strategy is not None):
            raise InvalidEvaluationPlanError(
                f"Template {self.name} has an invalid axis/strategy."
            )

    def applies_to(self, case: EvaluationCase) -> bool:
        """Preserve the seed axis, strategy and linguistic variety."""
        identifier = case.identifier
        return (
            identifier.axis is self.axis
            and identifier.strategy is self.strategy
            and identifier.variety in self.varieties
            and (
                not self.subject_domains
                or identifier.subject_domain in self.subject_domains
            )
            and (
                not self.risk_categories
                or identifier.risk_category in self.risk_categories
            )
            and (
                not self.owasp_categories
                or identifier.owasp_category in self.owasp_categories
            )
        )


@dataclass(frozen=True)
class TransformDefinition:
    """Properties needed to reject incompatible transform compositions."""

    name: str
    label: str
    needs_arabic: bool
    removes_arabic: bool
    is_template: bool
    safe_for_over_refusal: bool
    source: str
    strategies: frozenset[BypassStrategy] = field(
        default_factory=lambda: frozenset(BypassStrategy)
    )

    def applies_to(self, case: EvaluationCase) -> bool:
        """Check composition eligibility and OR meaning preservation."""
        if case.axis is Axis.OVER_REFUSAL:
            return self.safe_for_over_refusal
        return case.identifier.strategy in self.strategies


@dataclass(frozen=True)
class PromptVariant:
    """One concrete request and the recipe used to derive it from its seed."""

    variant_id: str
    arm_id: str
    sent_prompt: str
    template_name: str | None = None
    template_revision: str | None = None
    transform_names: tuple[str, ...] = ()
    content_sha256: str = ""
    review_status: str = "draft"
    source_urls: tuple[str, ...] = ()
    effective_strategies: tuple[BypassStrategy, ...] = ()


@dataclass(frozen=True)
class AdaptiveSettings:
    """A predeclared request budget and reproducible controller seed."""

    mode: EvaluationMode = EvaluationMode.STATIC
    attempt_budget: int = 8
    random_seed: int = 0

    def __post_init__(self) -> None:
        """Require a positive budget before any request is submitted."""
        if self.attempt_budget < 1:
            raise InvalidEvaluationPlanError(
                "The attempt budget K must be positive."
            )
