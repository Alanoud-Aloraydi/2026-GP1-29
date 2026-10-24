"""Evaluation cases sent to the target model."""

from dataclasses import dataclass

from harass.domain.case_identifier import CaseIdentifier
from harass.domain.errors import InvalidEvaluationCaseError
from harass.domain.taxonomy import Axis


@dataclass(frozen=True)
class EvaluationCase:
    """Pair an authored prompt with its evaluation objective.

    For over-refusal cases the objective is the safe request itself; for
    adversarial cases it is the harmful behavior the prompt tries to elicit,
    which can differ from the prompt wording.
    """

    identifier: CaseIdentifier
    prompt_text: str
    objective: str

    def __post_init__(self) -> None:
        """Reject cases without usable text."""
        if not self.prompt_text.strip():
            raise InvalidEvaluationCaseError(
                f"Case {self.identifier} has an empty prompt."
            )
        if not self.objective.strip():
            raise InvalidEvaluationCaseError(
                f"Case {self.identifier} has an empty objective."
            )

    @property
    def axis(self) -> Axis:
        """Return the safety axis of the case."""
        return self.identifier.axis
