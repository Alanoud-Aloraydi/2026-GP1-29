"""Convert persisted evaluation rows and restore UTC timestamps."""

from datetime import UTC, datetime

from harass.domain.evaluation_run import EvaluationRun, RunStatus
from harass.infrastructure.persistence.tables import (
    RunRow,
)


def new_run_row(run: EvaluationRun) -> RunRow:
    """Build a new run row."""
    return RunRow(
        run_id=run.run_id,
        owner_id=run.owner_id,
        connection_id=run.connection_id,
        target_model=run.target_model,
        status=run.status.value,
        created_at=run.created_at,
        lifecycle_events=[
            {"event": "created", "at": run.created_at.isoformat()}
        ],
        finished_at=run.finished_at,
        error=run.error,
    )


def read_run(row: RunRow) -> EvaluationRun:
    """Rebuild a domain run from a row."""
    return EvaluationRun(
        run_id=row.run_id,
        owner_id=row.owner_id,
        connection_id=row.connection_id,
        target_model=row.target_model,
        status=RunStatus(row.status),
        created_at=row.created_at.replace(tzinfo=UTC)
        if row.created_at.tzinfo is None
        else row.created_at,
        finished_at=utc_timestamp(row.finished_at),
        error=row.error,
        total_cases=row.total_cases,
        completed_cases=row.completed_cases,
        completed_attempts=row.completed_attempts,
        resumable=row.resumable,
        started_at=utc_timestamp(row.started_at),
        lifecycle_events=tuple(row.lifecycle_events or ()),
    )


def utc_timestamp(value: datetime | None) -> datetime | None:
    """Restore UTC metadata when SQLite returns timezone-naive timestamps."""
    return (
        value.replace(tzinfo=UTC)
        if value is not None and value.tzinfo is None
        else value
    )
