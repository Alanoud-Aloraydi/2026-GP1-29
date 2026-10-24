"""Port for one isolated target request followed by its verdicts."""

from abc import ABC, abstractmethod

from harass.domain.case_outcome import CaseOutcome
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.prompt_variant import PromptVariant
from harass.domain.target_connection import TargetConnection


class AttemptExecutor(ABC):
    """Execute an isolated variant with OWASP-specific context."""

    @abstractmethod
    async def execute(
        self,
        case: EvaluationCase,
        variant: PromptVariant,
        target: TargetConnection,
        run_identifier: str,
    ) -> CaseOutcome:
        """Execute an attempt and preserve any technical failure."""
