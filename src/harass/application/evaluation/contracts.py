"""Run parameters, requests and reports exchanged with the evaluation use case."""

from dataclasses import asdict, dataclass, field
from typing import Any

from harass.domain.case_outcome import CaseOutcome
from harass.domain.case_selection import CaseSelection
from harass.domain.metrics import EvaluationMetrics
from harass.domain.prompt_variant import AdaptiveSettings, EvaluationMode, VariantSelection
from harass.domain.target_connection import TargetConnection


@dataclass(frozen=True)
class RunParameters:
    """What a client chose for a run, besides which connection to evaluate."""

    selection: CaseSelection = field(default_factory=CaseSelection)
    include_baseline: bool = True
    max_base_cases_per_axis: int | None = None
    sampling_seed: int = 0
    variant_selection: VariantSelection = field(default_factory=VariantSelection)
    adaptive_settings: AdaptiveSettings = field(default_factory=AdaptiveSettings)

    def document(self) -> dict[str, Any]:
        """Return JSON-compatible job inputs without any target credentials."""
        document = asdict(self)
        document["selection"] = {
            key: sorted(value) if isinstance(value, frozenset) else value
            for key, value in document["selection"].items()
        }
        return document

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> "RunParameters":
        """Validate and decode parameters stored by `document`."""
        variants, adaptive = document["variant_selection"], document["adaptive_settings"]
        names = (variants["template_names"], variants["transform_names"])
        return cls(
            selection=CaseSelection.from_codes(**document["selection"]),
            include_baseline=document["include_baseline"],
            max_base_cases_per_axis=document["max_base_cases_per_axis"],
            sampling_seed=document["sampling_seed"],
            variant_selection=VariantSelection(
                *(None if value is None else tuple(value) for value in names)
            ),
            adaptive_settings=AdaptiveSettings(
                EvaluationMode(adaptive["mode"]),
                adaptive["attempt_budget"],
                adaptive["random_seed"],
            ),
        )


@dataclass(frozen=True)
class EvaluationRequest:
    """The model to evaluate, what to send it, and the run it belongs to."""

    target: TargetConnection
    parameters: RunParameters = field(default_factory=RunParameters)
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
    adaptive_settings: AdaptiveSettings = field(default_factory=AdaptiveSettings)
    variant_selection: VariantSelection | None = None
    selection: CaseSelection = field(default_factory=CaseSelection)
