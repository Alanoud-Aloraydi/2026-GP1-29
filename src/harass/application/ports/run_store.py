"""Port for persisting the lifecycle and results of evaluation runs."""

from abc import ABC, abstractmethod
from collections import Counter
from typing import Any

from harass.domain.evaluation_run import EvaluationRun


class RunStore(ABC):
    """Stores runs per owner and the report of each completed run."""

    def page_for_owner(self, owner_id: str, offset: int, limit: int) -> list[EvaluationRun]:
        """Provide bounded pages for simple adapters; databases override this query."""
        return self.list_for_owner(owner_id)[offset : offset + limit]

    def counts_for_owner(self, owner_id: str) -> dict[str, int]:
        """Count statuses without requiring a client to load every report."""
        return dict(Counter(item.status.value for item in self.list_for_owner(owner_id)))

    @abstractmethod
    def create(self, run: EvaluationRun) -> None:
        """Insert a new run."""

    @abstractmethod
    def update(self, run: EvaluationRun) -> None:
        """Replace the stored lifecycle fields of an existing run.

        Raises:
            UnknownRunError: If no run has that identifier for the owner.
        """

    @abstractmethod
    def save_report(self, run_id: str, document: dict[str, Any]) -> None:
        """Store the serialized report document of a completed run."""

    @abstractmethod
    def get(self, run_id: str, owner_id: str) -> EvaluationRun:
        """Return the owner's run.

        Raises:
            UnknownRunError: If the owner has no run with that identifier.
        """

    @abstractmethod
    def get_report(self, run_id: str, owner_id: str) -> dict[str, Any]:
        """Return the stored report document of the owner's completed run.

        Raises:
            UnknownRunError: If the run or its report does not exist for the owner.
        """

    @abstractmethod
    def list_for_owner(self, owner_id: str) -> list[EvaluationRun]:
        """Return the owner's runs, most recent first."""
