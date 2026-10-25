"""Persist queued work with shared judge admission and leases."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, or_, select, update

from harass.application.errors import (
    ActiveRunError,
    ApplicationError,
    ConflictError,
    UnknownRunError,
)
from harass.application.ports.evaluation_journal import EvaluationJournal
from harass.application.ports.run_queue import LeaseLostError, RunJob, RunQueue
from harass.domain.evaluation_run import EvaluationRun, RunStatus
from harass.infrastructure.persistence.job_sessions import (
    job_session,
    owned_job,
)
from harass.infrastructure.persistence.row_mapping import new_run_row, read_run
from harass.infrastructure.persistence.session_factory import SessionFactory
from harass.infrastructure.persistence.sqlalchemy_journal import (
    SqlAlchemyEvaluationJournal,
    stored_documents,
)
from harass.infrastructure.persistence.tables import (
    ReportRow,
    RunJobRow,
    RunOutcomeRow,
    RunRow,
    UserRow,
    WorkerPresenceRow,
    WorkerSlotRow,
)
from harass.infrastructure.persistence.upsert import insert_for


class SqlAlchemyRunQueue(RunQueue):
    """Admit one active worker per judge through database leases."""

    def __init__(
        self,
        factory: SessionFactory,
        execution_profile: str,
        slot_key: str,
        *,
        lease_seconds: int = 120,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Retain the immutable execution profile and worker lease settings."""
        self._factory = factory
        self._profile = execution_profile
        self._slot = slot_key
        self._lease_seconds = lease_seconds
        self._clock = clock

    def enqueue(
        self,
        run: EvaluationRun,
        parameters: dict[str, Any],
        target_endpoint: str,
    ) -> None:
        """Persist run admission and its durable job atomically."""
        with job_session(self._factory) as session:
            session.scalar(
                select(UserRow.user_id)
                .where(UserRow.user_id == run.owner_id)
                .with_for_update()
            )
            active = session.scalar(
                select(RunRow.run_id)
                .where(
                    RunRow.owner_id == run.owner_id,
                    RunRow.status.in_(["pending", "running"])
                    | RunRow.resumable,
                )
                .limit(1)
            )
            if active:
                raise ActiveRunError(active)
            session.add(new_run_row(run))
            session.flush()
            session.add(
                RunJobRow(
                    run_id=run.run_id,
                    parameters=parameters,
                    target_endpoint=target_endpoint,
                    execution_profile=self._profile,
                    checkpoint={},
                    revision=0,
                    queued_at=run.created_at,
                    connection_revision=parameters.get("connection_revision"),
                )
            )

    def heartbeat(self) -> None:
        """Record worker liveness independently of active job leases."""
        with job_session(self._factory) as session:
            session.execute(
                insert_for(session, WorkerPresenceRow)
                .values(slot_key=self._slot, last_seen=self._clock())
                .on_conflict_do_update(
                    index_elements=["slot_key"],
                    set_={"last_seen": self._clock()},
                )
            )

    def worker_available(self) -> bool:
        """Check for a recent worker heartbeat."""
        with job_session(self._factory) as session:
            row = session.get(WorkerPresenceRow, self._slot)
            if row is None:
                return False
            seen = (
                row.last_seen
                if row.last_seen.tzinfo
                else row.last_seen.replace(tzinfo=UTC)
            )
            return (self._clock() - seen).total_seconds() < 60

    def claim(self, worker_id: str) -> RunJob | None:
        """Acquire the judge slot and claim an eligible run."""
        now = self._clock()
        until = now + timedelta(seconds=self._lease_seconds)
        with job_session(self._factory) as session:
            acquired = session.scalar(
                insert_for(session, WorkerSlotRow)
                .values(
                    slot_key=self._slot, worker_id=worker_id, lease_until=until
                )
                .on_conflict_do_update(
                    index_elements=["slot_key"],
                    set_={"worker_id": worker_id, "lease_until": until},
                    where=WorkerSlotRow.lease_until <= now,
                )
                .returning(WorkerSlotRow.slot_key)
            )
            if acquired is None:
                return None
            row = session.scalar(
                select(RunJobRow)
                .join(RunRow)
                .where(
                    RunRow.status.in_(
                        [RunStatus.PENDING.value, RunStatus.RUNNING.value]
                    ),
                    or_(
                        RunJobRow.worker_id.is_(None),
                        RunJobRow.lease_until <= now,
                    ),
                )
                .order_by(
                    func.coalesce(RunJobRow.queued_at, RunRow.created_at),
                    RunRow.run_id,
                )
                .limit(1)
                .with_for_update(of=RunJobRow, skip_locked=True)
            )
            if row is None:
                session.execute(
                    delete(WorkerSlotRow).where(
                        WorkerSlotRow.slot_key == self._slot
                    )
                )
                return None
            run = session.get(RunRow, row.run_id)
            if run is None:
                raise UnknownRunError(row.run_id)
            if row.execution_profile != self._profile:
                run.status = RunStatus.FAILED.value
                run.error = (
                    "Execution configuration changed; create a new run."
                )
                run.finished_at = now
                session.execute(
                    delete(WorkerSlotRow).where(
                        WorkerSlotRow.slot_key == self._slot
                    )
                )
                return None
            row.worker_id, row.lease_until = worker_id, until
            run.status = RunStatus.RUNNING.value
            if run.started_at is None:
                run.started_at = now
                _event(run, "started", now)
            return RunJob(
                read_run(run),
                row.parameters,
                row.target_endpoint,
                worker_id,
                row.connection_revision,
            )

    def renew(self, job: RunJob) -> None:
        """Renew both leases without reclaiming an expired slot."""
        now = self._clock()
        with job_session(self._factory) as session:
            row = owned_job(session, job, now)
            until = now + timedelta(seconds=self._lease_seconds)
            acquired = session.scalar(
                update(WorkerSlotRow)
                .where(
                    WorkerSlotRow.slot_key == self._slot,
                    WorkerSlotRow.worker_id == job.worker_id,
                    WorkerSlotRow.lease_until > now,
                )
                .values(lease_until=until)
                .returning(WorkerSlotRow.slot_key)
            )
            if acquired is None:
                raise LeaseLostError("Shared judge lease was lost.")
            row.lease_until = until

    def release(self, job: RunJob) -> None:
        """Make unfinished work recoverable without losing progress."""
        with job_session(self._factory) as session:
            released = session.scalar(
                update(RunJobRow)
                .where(
                    RunJobRow.run_id == job.run.run_id,
                    RunJobRow.worker_id == job.worker_id,
                )
                .values(
                    worker_id=None, lease_until=None, queued_at=self._clock()
                )
                .returning(RunJobRow.run_id)
            )
            if released is not None:
                session.execute(
                    update(RunRow)
                    .where(
                        RunRow.run_id == released,
                        RunRow.status == RunStatus.RUNNING.value,
                    )
                    .values(status=RunStatus.PENDING.value)
                )
            session.execute(
                delete(WorkerSlotRow).where(
                    WorkerSlotRow.slot_key == self._slot,
                    WorkerSlotRow.worker_id == job.worker_id,
                )
            )

    def finish(self, job: RunJob, document: dict[str, Any]) -> None:
        """Complete the owned run while retaining paged evidence."""
        self._finish(job, RunStatus.COMPLETED, document=document)

    def fail(
        self, job: RunJob, error: str, *, resumable: bool = False
    ) -> None:
        """Preserve partial evidence when a permanently invalid run fails."""
        self._finish(job, RunStatus.FAILED, error=error, resumable=resumable)

    def _finish(
        self,
        job: RunJob,
        status: RunStatus,
        *,
        document: dict[str, Any] | None = None,
        error: str | None = None,
        resumable: bool = False,
    ) -> None:
        """Atomically finalize an owned job and its compact report summary."""
        with job_session(self._factory) as session:
            row = owned_job(session, job, self._clock())
            finished = session.scalar(
                update(RunJobRow)
                .where(
                    RunJobRow.run_id == row.run_id,
                    RunJobRow.worker_id == job.worker_id,
                )
                .values(worker_id=None, lease_until=None)
                .returning(RunJobRow.run_id)
            )
            if finished is None:
                raise LeaseLostError(
                    "The run was reclaimed before completion."
                )
            run = session.get(RunRow, row.run_id)
            if run is None:
                raise UnknownRunError(row.run_id)
            if document is not None:
                document = {
                    **document,
                    "execution_profile": row.execution_profile,
                    "plan_fingerprint": row.plan_fingerprint,
                }
                session.execute(
                    insert_for(session, ReportRow)
                    .values(
                        run_id=row.run_id,
                        document=document,
                    )
                    .on_conflict_do_update(
                        index_elements=["run_id"], set_={"document": document}
                    )
                )
                run.target_model = document["target_model"]
            run.status, run.error, run.finished_at = (
                status.value,
                error,
                self._clock(),
            )
            _event(
                run,
                "suspended" if resumable else status.value,
                run.finished_at,
            )
            run.resumable = resumable
            session.execute(
                delete(WorkerSlotRow).where(
                    WorkerSlotRow.slot_key == self._slot,
                    WorkerSlotRow.worker_id == job.worker_id,
                )
            )

    def resume(self, run_id: str, owner_id: str) -> EvaluationRun:
        """Requeue suspended work without resetting its observations."""
        with job_session(self._factory) as session:
            run = session.scalar(
                select(RunRow).where(RunRow.run_id == run_id).with_for_update()
            )
            if run is None or run.owner_id != owner_id:
                raise UnknownRunError(run_id)
            job = session.get(RunJobRow, run_id)
            if (
                run.status != RunStatus.FAILED.value
                or not run.resumable
                or job is None
            ):
                raise ApplicationError(
                    "This run has no resumable suspended state."
                )
            if job.execution_profile != self._profile:
                raise ApplicationError(
                    "Execution configuration changed; create a new run."
                )
            job.checkpoint = {**job.checkpoint, "technical_failures": 0}
            job.worker_id, job.lease_until = None, None
            job.queued_at = self._clock()
            _event(run, "resumed", self._clock())
            job.revision += 1
            run.status, run.error, run.finished_at, run.resumable = (
                RunStatus.PENDING.value,
                None,
                None,
                False,
            )
            return read_run(run)

    def cancel(self, run_id: str, owner_id: str) -> EvaluationRun:
        """Fence worker writes while preserving durable attempt state."""
        with job_session(self._factory) as session:
            run = session.scalar(
                select(RunRow).where(RunRow.run_id == run_id).with_for_update()
            )
            if run is None or run.owner_id != owner_id:
                raise UnknownRunError(run_id)
            if (
                run.status
                not in {RunStatus.PENDING.value, RunStatus.RUNNING.value}
                and not run.resumable
            ):
                raise ConflictError("This evaluation is already finished.")
            job = session.get(RunJobRow, run_id, with_for_update=True)
            if job is not None:
                job.worker_id, job.lease_until = None, None
                job.revision += 1
            run.status, run.resumable = RunStatus.CANCELLED.value, False
            run.finished_at = self._clock()
            _event(run, "cancelled", run.finished_at)
            return read_run(run)

    def journal(self, job: RunJob) -> EvaluationJournal:
        """Bind writes to this run's worker identity."""
        return SqlAlchemyEvaluationJournal(self._factory, job, self._clock)

    def outcome_page(
        self, run_id: str, owner_id: str, offset: int, limit: int
    ) -> dict[str, Any]:
        """Read one bounded evidence page only after validating ownership."""
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError(
                "Evidence pages require offset >= 0 and limit 1-100."
            )
        with job_session(self._factory) as session:
            run = session.get(RunRow, run_id)
            if run is None or run.owner_id != owner_id:
                raise UnknownRunError(run_id)
            total = (
                session.scalar(
                    select(func.count())
                    .select_from(RunOutcomeRow)
                    .where(RunOutcomeRow.run_id == run_id)
                )
                or 0
            )
            rows = session.scalars(
                select(RunOutcomeRow.document)
                .where(
                    RunOutcomeRow.run_id == run_id,
                )
                .order_by(
                    RunOutcomeRow.case_index, RunOutcomeRow.attempt_number
                )
                .offset(offset)
                .limit(limit)
            )
            return {
                "total": total,
                "offset": offset,
                "limit": limit,
                "items": list(rows),
            }

    def outcome_documents(
        self, run_id: str, owner_id: str
    ) -> Iterator[dict[str, Any]]:
        """Stream committed evidence after validating ownership."""
        with job_session(self._factory) as session:
            run = session.get(RunRow, run_id)
            if run is None or run.owner_id != owner_id:
                raise UnknownRunError(run_id)
        yield from stored_documents(self._factory, run_id)


def _event(run: RunRow, name: str, timestamp: datetime) -> None:
    """Append an observed lifecycle transition."""
    run.lifecycle_events = [
        *(run.lifecycle_events or []),
        {"event": name, "at": timestamp.isoformat()},
    ]
