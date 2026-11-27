"""Run parameters, requests and reports exchanged with the evaluation use case."""

from dataclasses import asdict, dataclass, field
from typing import Any

from harass.domain.case_outcome import CaseOutcome
from harass.domain.case_selection import CaseSelection
from harass.domain.metrics import EvaluationMetrics
from harass.domain.target_connection import TargetConnection
from harass.domain.taxonomy import ArabicVariety, Axis

MAX_ROUNDS = 5
MAX_PROMPTS_PER_ROUND = 50


@dataclass(frozen=True)
class RunParameters:
    """What a client chose for a run, besides which connection to evaluate."""

    selection: CaseSelection = field(default_factory=CaseSelection)
    max_base_cases_per_axis: int | None = None
    sampling_seed: int = 0

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
        return cls(
            selection=CaseSelection.from_codes(**document["selection"]),
            max_base_cases_per_axis=document["max_base_cases_per_axis"],
            sampling_seed=document["sampling_seed"],
        )


@dataclass(frozen=True)
class AgenticParameters:
    """What a client chose for an agentic run.

    Each round writes ``prompts_per_round`` prompts on each of ``axes``.
    ``baseline_run_id`` names the baseline run on the same connection whose
    refusals and successful attacks seed the pattern cards; the run starts
    only once that baseline has completed.
    ``transform_names`` are the adapter's transforms; ``varieties`` limits the
    written varieties, every variety when empty.
    """

    baseline_run_id: str
    axes: tuple[Axis, ...] = (Axis.OVER_REFUSAL, Axis.ADVERSARIAL)
    rounds: int = 3
    prompts_per_round: int = 20
    transform_names: tuple[str, ...] = ()
    varieties: frozenset[ArabicVariety] = frozenset()

    def __post_init__(self) -> None:
        """Reject a run outside the bounds a worker quantum can hold.

        Raises: ValueError: If no axis or a repeated axis is chosen, or the
        rounds or prompts per round are out of range.
        """
        if not self.axes or len(set(self.axes)) != len(self.axes):
            raise ValueError("Choose each axis at most once, and at least one.")
        if not 1 <= self.rounds <= MAX_ROUNDS:
            raise ValueError(f"Rounds must be between 1 and {MAX_ROUNDS}.")
        if not 1 <= self.prompts_per_round <= MAX_PROMPTS_PER_ROUND:
            raise ValueError(f"Prompts per round must be between 1 and {MAX_PROMPTS_PER_ROUND}.")

    def document(self) -> dict[str, Any]:
        """Return JSON-compatible job inputs without any target credentials."""
        return {
            "baseline_run_id": self.baseline_run_id,
            "axes": [str(axis) for axis in self.axes],
            "rounds": self.rounds,
            "prompts_per_round": self.prompts_per_round,
            "transform_names": list(self.transform_names),
            "varieties": sorted(self.varieties),
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> "AgenticParameters":
        """Validate and decode parameters stored by `document`."""
        return cls(
            baseline_run_id=document["baseline_run_id"],
            axes=tuple(map(Axis, document["axes"])),
            rounds=document["rounds"],
            prompts_per_round=document["prompts_per_round"],
            transform_names=tuple(document["transform_names"]),
            varieties=frozenset(map(ArabicVariety, document["varieties"])),
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
    outcomes: tuple[CaseOutcome, ...]
    metrics: EvaluationMetrics
    selection: CaseSelection = field(default_factory=CaseSelection)
