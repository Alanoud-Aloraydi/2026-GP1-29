"""The lifecycle record of one evaluation run managed by the backend."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class RunStatus(StrEnum):
    """Where a run is in its lifecycle."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class EvaluationRun:
    """What a client asked to evaluate and how far it has got.

    The run holds only identifiers and status; the outcomes and metrics are
    stored with the report once the run completes. ``error`` is set only for a
    failed run.
    """

    run_id: str
    owner_id: str
    connection_id: str
    target_model: str
    status: RunStatus
    created_at: datetime
    finished_at: datetime | None = None
    error: str | None = None
    total_cases: int = 0
    completed_cases: int = 0
    completed_attempts: int = 0
    resumable: bool = False
    started_at: datetime | None = None
    lifecycle_events: tuple[dict[str, str], ...] = ()
    worker_available: bool | None = None
