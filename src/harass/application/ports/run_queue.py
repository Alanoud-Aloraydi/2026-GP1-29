"""Durable run admission, worker leases and paged evidence."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from harass.application.errors import ApplicationError
from harass.application.ports.evaluation_journal import EvaluationJournal
from harass.application.ports.run_admission import RunAdmission
from harass.domain.evaluation_run import EvaluationRun


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
    def fail(
        self, job: RunJob, error: str, *, resumable: bool = False
    ) -> None:
        """Fail owned work without exposing provider exception details."""

    @abstractmethod
    def journal(self, job: RunJob) -> EvaluationJournal:
        """Return a journal fenced to this worker's lease."""
