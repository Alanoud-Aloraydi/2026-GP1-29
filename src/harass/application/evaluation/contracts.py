"""Request and report data exchanged with the evaluation use case."""

from dataclasses import dataclass, field

from harass.domain.case_outcome import CaseOutcome
from harass.domain.case_selection import CaseSelection
from harass.domain.metrics import EvaluationMetrics
from harass.domain.prompt_variant import AdaptiveSettings, VariantSelection
from harass.domain.target_connection import TargetConnection


@dataclass(frozen=True)
class EvaluationRequest:
    """Evaluation target, selection and execution settings."""

    target: TargetConnection
    selection: CaseSelection = field(default_factory=CaseSelection)
    include_baseline: bool = True
    max_base_cases_per_axis: int | None = None
    sampling_seed: int = 0
    variant_selection: VariantSelection = field(
        default_factory=VariantSelection
    )
    adaptive_settings: AdaptiveSettings = field(
        default_factory=AdaptiveSettings
    )
    run_identifier: str | None = None


@dataclass(frozen=True)
class EvaluationReport:
    """Outcomes and metrics of one evaluation run."""

    run_identifier: str
    target_model: str
    variant_names: tuple[str, ...]
    include_baseline: bool
    outcomes: tuple[CaseOutcome, ...]
    metrics: EvaluationMetrics
    adaptive_settings: AdaptiveSettings = field(
        default_factory=AdaptiveSettings
    )
    variant_selection: VariantSelection | None = None
    selection: CaseSelection = field(default_factory=CaseSelection)
