"""Owner-facing admission, lifecycle and evidence access for durable runs."""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any

from harass.application.errors import ApplicationError
from harass.domain.evaluation_run import EvaluationRun


class RunAdmission(ABC):
    """Expose run management without granting worker lease operations."""

    def worker_available(self) -> bool | None:
        """Return unknown when the adapter has no worker monitoring."""
        return None

    @abstractmethod
    def enqueue(
        self, run: EvaluationRun, parameters: dict[str, Any], endpoint: str
    ) -> None:
        """Persist admission and immutable execution inputs atomically."""

    @abstractmethod
    def cancel(self, run_id: str, owner_id: str) -> EvaluationRun:
        """Cancel owned work while retaining committed evidence."""

    @abstractmethod
    def resume(self, run_id: str, owner_id: str) -> EvaluationRun:
        """Resume owned work under its original execution configuration."""

    @abstractmethod
    def outcome_page(
        self, run_id: str, owner_id: str, offset: int, limit: int
    ) -> dict[str, Any]:
        """Read a bounded page of owner-scoped attempt evidence."""

    def outcome_documents(
        self, run_id: str, owner_id: str
    ) -> Iterator[dict[str, Any]]:
        """Stream evidence and reject inconsistent pagination progress."""
        offset = 0
        while True:
            page = self.outcome_page(run_id, owner_id, offset, 100)
            if not page["items"] and offset < page["total"]:
                raise ApplicationError("Stored evidence is incomplete.")
            yield from page["items"]
            offset += len(page["items"])
            if offset >= page["total"]:
                return
