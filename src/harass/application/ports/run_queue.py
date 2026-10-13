"""Durable run admission, worker leases and paged evidence."""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from harass.application.errors import ApplicationError
from harass.application.ports.evaluation_journal import EvaluationJournal
from harass.domain.evaluation_run import EvaluationRun


class LeaseLostError(ApplicationError):
    """The worker no longer owns this run and must stop submitting requests."""


class StorageUnavailableError(ApplicationError):
    """Durable storage is unavailable; uncommitted work must not be retried blindly."""


class EvaluationSuspendedError(ApplicationError):
    """Repeated technical failures require recovery before more budget is consumed."""


class EvaluationYieldedError(ApplicationError):
    """A committed work quantum yields the judge slot to another queued run."""


@dataclass(frozen=True)
class RunJob:
    """A leased run and its immutable execution parameters, without API credentials."""

    run: EvaluationRun
    parameters: dict[str, Any]
    target_endpoint: str
    worker_id: str
    connection_revision: int | None = None


class RunQueue(ABC):
    """Coordinate workers through durable, fenced ownership of queued runs."""

    def heartbeat(self) -> None:
        """Publish worker liveness when the adapter supports durable monitoring."""
        return None

    def worker_available(self) -> bool | None:
        """Return unknown for adapters without durable worker monitoring."""
        return None

    def cancel(self, run_id: str, owner_id: str) -> EvaluationRun:
        """Cancel owner-scoped durable work if the adapter supports it."""
        raise ApplicationError("Cancellation is unavailable for this adapter.")

    @abstractmethod
    def enqueue(
        self, run: EvaluationRun, parameters: dict[str, Any], target_endpoint: str
    ) -> None:
        """Atomically persist the run and its job before returning a run identifier."""

    @abstractmethod
    def claim(self, worker_id: str) -> RunJob | None:
        """Lease the oldest eligible run while holding the shared judge slot."""

    @abstractmethod
    def renew(self, job: RunJob) -> None:
        """Renew ownership or raise LeaseLostError before further submissions."""

    @abstractmethod
    def release(self, job: RunJob) -> None:
        """Release an unfinished run for recovery without discarding its checkpoint."""

    @abstractmethod
    def finish(self, job: RunJob, document: dict[str, Any]) -> None:
        """Atomically store the final summary and complete the owned run."""

    @abstractmethod
    def fail(self, job: RunJob, error: str, *, resumable: bool = False) -> None:
        """Mark a permanently invalid owned run failed without exposing exception content."""

    @abstractmethod
    def resume(self, run_id: str, owner_id: str) -> EvaluationRun:
        """Requeue saved progress only for its owner and an unchanged execution profile."""

    @abstractmethod
    def journal(self, job: RunJob) -> EvaluationJournal:
        """Return a journal fenced to this worker's lease."""

    @abstractmethod
    def outcome_page(self, run_id: str, owner_id: str, offset: int, limit: int) -> dict[str, Any]:
        """Return an owner-scoped bounded page of attempt evidence."""

    def outcome_documents(self, run_id: str, owner_id: str) -> Iterator[dict[str, Any]]:
        """Iterate evidence pages; adapters may use keyset pagination for exports."""
        offset = 0
        while True:
            page = self.outcome_page(run_id, owner_id, offset, 100)
            yield from page["items"]
            offset += len(page["items"])
            if offset >= page["total"]:
                return
