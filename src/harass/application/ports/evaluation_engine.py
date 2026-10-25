"""Port for executing an evaluation plan against a model."""

from abc import ABC, abstractmethod

from harass.application.ports.evaluation_journal import EvaluationJournal
from harass.domain.case_outcome import CaseOutcome
from harass.domain.evaluation_plan import EvaluationPlan
from harass.domain.target_connection import TargetConnection


class EvaluationEngine(ABC):
    """Execute evaluation plans and collect scored outcomes."""

    @abstractmethod
    async def evaluate(
        self,
        plan: EvaluationPlan,
        target: TargetConnection,
        run_identifier: str,
        *,
        journal: EvaluationJournal | None = None,
    ) -> list[CaseOutcome]:
        """Evaluate selected recipes and any planned baseline.

        Outcomes whose verdict could not be obtained carry an error instead of
        being omitted.
        """
