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


class RunKind(StrEnum):
    """What a run sends: the dataset as written, or prompts it generates."""

    BASELINE = "baseline"
    AGENTIC = "agentic"


# Work that still holds the owner's single evaluation slot.
ACTIVE_STATUSES = (RunStatus.PENDING, RunStatus.RUNNING)


@dataclass(frozen=True)
class EvaluationRun:
    """What a client asked to evaluate and how far it has got.

    The run holds only identifiers and status; the outcomes and metrics are
    stored with the report once the run completes. ``error`` is set only for a
    failed run. ``total_cases`` and ``completed_cases`` count dataset cases in
    a baseline run and generation rounds per axis in an agentic run.
    ``awaits_run_id`` names the baseline run an agentic run waits for. It is
    cleared once that baseline completes and the agentic run may start, and
    kept on an agentic run that failed because its baseline stopped.
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
    resumable: bool = False
    started_at: datetime | None = None
    lifecycle_events: tuple[dict[str, str], ...] = ()
    worker_available: bool | None = None
    kind: RunKind = RunKind.BASELINE
    awaits_run_id: str | None = None
