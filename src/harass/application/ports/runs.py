"""Ports for reading runs, admitting them and leasing them to workers."""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from harass.application.errors import ApplicationError
from harass.application.ports.evaluation import EvaluationJournal
from harass.domain.case_selection import CaseSelection
from harass.domain.evaluation_run import EvaluationRun


class RunStore(ABC):
    """Reads the runs of each owner; the run queue writes them."""

    @abstractmethod
    def get(self, run_id: str, owner_id: str) -> EvaluationRun:
        """Return one run of the owner.

        Raises: UnknownRunError: If the owner has no run with that identifier.
        """

    @abstractmethod
    def get_report(self, run_id: str, owner_id: str) -> dict[str, Any]:
        """Return the stored report document of the owner's completed run.

        Raises: UnknownRunError: If the run or its report does not exist for the owner.
        """

    @abstractmethod
    def page_for_owner(self, owner_id: str, offset: int, limit: int) -> list[EvaluationRun]:
        """Return one page of the owner's runs, most recent first."""

    @abstractmethod
    def counts_for_owner(self, owner_id: str) -> dict[str, int]:
        """Count the owner's runs in each status."""

    @abstractmethod
    def baselines(
        self, owner_id: str, connection_id: str
    ) -> list[tuple[EvaluationRun, CaseSelection]]:
        """Return the owner's baseline runs on a connection that completed or may still.

        Each comes with the case selection it ran, so a caller can match its
        axes and varieties, newest first. Cancelled and permanently failed
        runs are left out.
        """


class RunAdmission(ABC):
    """Expose run management without granting worker lease operations."""

    def worker_available(self) -> bool | None:
        """Return unknown when the adapter has no worker monitoring."""
        return None

    @abstractmethod
    def enqueue(self, run: EvaluationRun, parameters: dict[str, Any], endpoint: str) -> None:
        """Persist admission and immutable execution inputs atomically."""

    @abstractmethod
    def cancel(self, run_id: str, owner_id: str) -> EvaluationRun:
        """Cancel owned work while retaining committed evidence."""

    @abstractmethod
    def resume(self, run_id: str, owner_id: str) -> EvaluationRun:
        """Resume owned work under its original execution configuration."""

    @abstractmethod
    def outcome_page(self, run_id: str, owner_id: str, offset: int, limit: int) -> dict[str, Any]:
        """Read a bounded page of owner-scoped attempt evidence."""

    def outcome_documents(self, run_id: str, owner_id: str) -> Iterator[dict[str, Any]]:
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


class LeaseLostError(ApplicationError):
    """The worker no longer owns this run and must stop submitting requests."""


class StorageUnavailableError(ApplicationError):
    """Durable storage cannot confirm committed work."""


class EvaluationSuspendedError(ApplicationError):
    """Repeated technical failures require evaluation recovery."""


class EvaluationYieldedError(ApplicationError):
    """A committed work quantum yields the judge slot to another queued run."""


@dataclass(frozen=True)
class RunJob:
    """Describe leased work without storing API credentials."""

    run: EvaluationRun
    parameters: dict[str, Any]
    target_endpoint: str
    worker_id: str
    connection_revision: int | None = None


class RunQueue(RunAdmission, ABC):
    """Coordinate workers through durable, fenced ownership of queued runs."""

    def heartbeat(self) -> None:
        """Publish worker liveness through the durable adapter."""
        return None

    @abstractmethod
    def claim(self, worker_id: str) -> RunJob | None:
        """Lease eligible work while holding the shared judge slot."""

    @abstractmethod
    def renew(self, job: RunJob) -> None:
        """Renew ownership or raise LeaseLostError."""

    @abstractmethod
    def release(self, job: RunJob) -> None:
        """Release unfinished work while preserving its checkpoint."""

    @abstractmethod
    def finish(self, job: RunJob, document: dict[str, Any]) -> None:
        """Atomically store the final summary and complete the owned run."""

    @abstractmethod
    def fail(self, job: RunJob, error: str, *, resumable: bool = False) -> None:
        """Fail owned work without exposing provider exception details."""

    @abstractmethod
    def journal(self, job: RunJob) -> EvaluationJournal:
        """Return a journal fenced to this worker's lease."""
