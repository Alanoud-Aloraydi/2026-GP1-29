"""Transactional job storage and worker ownership checks."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from harass.application.errors import ConflictError
from harass.application.ports.run_queue import (
    LeaseLostError,
    RunJob,
    StorageUnavailableError,
)
from harass.infrastructure.persistence.session_factory import SessionFactory
from harass.infrastructure.persistence.tables import RunJobRow


@contextmanager
def job_session(factory: SessionFactory) -> Iterator[Session]:
    """Roll back storage failures without exposing provider details."""
    try:
        with factory() as session, session.begin():
            yield session
    except IntegrityError as error:
        constraint = getattr(
            getattr(error.orig, "diag", None), "constraint_name", None
        )
        if constraint == "uq_runs_active_owner" or "runs.owner_id" in str(
            error.orig
        ):
            raise ConflictError(
                "Finish or cancel the current evaluation "
                "before starting another."
            ) from error
        raise
    except OperationalError as error:
        raise StorageUnavailableError(
            "Run storage is temporarily unavailable."
        ) from error


def owned_job(
    session: Session, job: RunJob, now: datetime | None = None
) -> RunJobRow:
    """Lock a valid lease and reject expired or superseded workers."""
    row = session.scalar(
        select(RunJobRow)
        .where(
            RunJobRow.run_id == job.run.run_id,
            RunJobRow.worker_id == job.worker_id,
            RunJobRow.lease_until > (now or datetime.now(UTC)),
        )
        .with_for_update()
    )
    if row is None:
        raise LeaseLostError("Worker lease was lost.")
    return row
