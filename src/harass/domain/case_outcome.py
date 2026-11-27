"""Judged outcome of sending one case to the evaluated model."""

from dataclasses import dataclass

from harass.domain.comprehension import ComprehensionSignal
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.taxonomy import Axis, ResponseCategory


@dataclass(frozen=True)
class JudgeTrace:
    """Record judge calls, vote budgets and measured elapsed time."""

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


@dataclass(frozen=True)
class CaseOutcome:
    """Verdicts for one case; ``error`` marks a missing verdict.

    ``attack_succeeded`` applies to adversarial cases only.
    ``comprehension_signal`` is a rule suspicion of an unclear response kept
    beside the judge's ``response_category``, never merged into it.
    """

    case: EvaluationCase
    response_category: ResponseCategory | None = None
    attack_succeeded: bool | None = None
    error: str | None = None
    transcript: AttemptTranscript | None = None
    scenario_name: str | None = None
    leak_exact_match: bool | None = None
    leak_rouge_l: float | None = None
    submission_uncertain: bool = False
    technical_error: str | None = None
    judge_requests: tuple[dict[str, object], ...] = ()
    elapsed_seconds: float | None = None
    comprehension_signal: ComprehensionSignal | None = None

    @property
    def is_scored(self) -> bool:
        """Check that all verdicts required by the case axis are present."""
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
