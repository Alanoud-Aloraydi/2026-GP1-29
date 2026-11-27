"""Ports for evaluation cases, attempts, engines and journals."""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any

from harass.domain.case_outcome import CaseOutcome
from harass.domain.case_selection import CaseSelection
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.evaluation_plan import EvaluationPlan
from harass.domain.target_connection import TargetConnection


class SeedSource(ABC):
    """Provides evaluation cases from a seed store."""

    @abstractmethod
    def load_cases(self, selection: CaseSelection) -> list[EvaluationCase]:
        """Load selected cases in identifier order.

        Raises: SeedSourceError: If the seed data cannot be read or violates
        the seed schema.
        """


class AttemptExecutor(ABC):
    """Send one prompt for a case in its OWASP context and judge the reply."""

    @abstractmethod
    async def execute(
        self, case: EvaluationCase, sent_prompt: str, target: TargetConnection, run_identifier: str
    ) -> CaseOutcome:
        """Execute an attempt and preserve any technical failure."""


class EvaluationJournal(ABC):
    """Commit outcomes and progress before the next submission."""

    @abstractmethod
    def initialize(self, fingerprint: str, total_cases: int) -> dict[str, Any]:
        """Return the checkpoint, rejecting a changed evaluation plan."""

    @abstractmethod
    def reserve(self, checkpoint: dict[str, Any]) -> None:
        """Persist the next submission before making its external request."""

    @abstractmethod
    def commit(self, outcome: CaseOutcome, checkpoint: dict[str, Any]) -> None:
        """Atomically persist an outcome and the checkpoint that follows it."""

    @abstractmethod
    def outcomes(self, *, lightweight: bool = False) -> Iterator[CaseOutcome]:
        """Stream stored outcomes with optional transcript omission."""


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
        """Send every planned case once and judge each reply.

        Outcomes whose verdict could not be obtained carry an error instead of
        being omitted.
        """
