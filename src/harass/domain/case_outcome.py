"""Judged outcome of sending one case using an auditable prompt recipe."""

from dataclasses import dataclass, field

from harass.domain.evaluation_case import EvaluationCase
from harass.domain.prompt_variant import PromptVariant
from harass.domain.taxonomy import Axis, ResponseCategory

BASELINE_VARIANT_NAME = "baseline"


@dataclass(frozen=True)
class JudgeTrace:
    """Actual verdict calls within a fixed vote budget, with measured elapsed time."""

    vote_budget: int
    votes: tuple[str, ...]
    elapsed_seconds: float


@dataclass(frozen=True)
class AttemptTranscript:
    """What was sent, what came back and why the judge decided as it did."""

    sent_prompt: str
    response: str
    category_rationale: str | None = None
    attack_rationale: str | None = None
    category_judge: JudgeTrace | None = None
    attack_judge: JudgeTrace | None = None
    target_metadata: dict[str, object] = field(default_factory=dict)



@dataclass(frozen=True)
class CaseOutcome:
    """Verdicts for one case and recipe; ``error`` marks a missing verdict.

    ``variant_name`` is ``BASELINE_VARIANT_NAME`` when the prompt was sent without conversion.
    ``attack_succeeded`` applies to adversarial cases only.
    """

    case: EvaluationCase
    variant_name: str
    response_category: ResponseCategory | None = None
    attack_succeeded: bool | None = None
    error: str | None = None
    transcript: AttemptTranscript | None = None
    variant: PromptVariant | None = None
    attempt_number: int = 0
    stop_reason: str | None = None
    posterior_before: tuple[int, int] | None = None
    scenario_name: str | None = None
    leak_exact_match: bool | None = None
    leak_rouge_l: float | None = None
    submission_uncertain: bool = False
    technical_error: str | None = None
    judge_requests: tuple[dict[str, object], ...] = ()
    elapsed_seconds: float | None = None
    needs_review: bool = False

    @property
    def is_attack_scored(self) -> bool:
        """Return whether an adversarial success verdict is available."""
        return (
            self.case.axis is Axis.ADVERSARIAL
            and self.attack_succeeded is not None
            and self.technical_error is None
            and not self.submission_uncertain
        )

    @property
    def is_category_scored(self) -> bool:
        """Return whether a response category verdict is available."""
        return (
            self.response_category is not None
            and self.technical_error is None
            and not self.submission_uncertain
        )


    @property
    def is_scored(self) -> bool:
        """Return whether every verdict required by the case's axis is present."""
        if self.error is not None or self.response_category is None:
            return False
        return self.case.axis is Axis.OVER_REFUSAL or self.attack_succeeded is not None

    @property
    def is_refusal(self) -> bool:
        """Return whether the response was a partial or full refusal."""
        return self.response_category in {
            ResponseCategory.PARTIAL_REFUSAL,
            ResponseCategory.FULL_REFUSAL,
        }
