"""Commit attempt evidence under fenced worker leases."""

from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from harass.application.errors import EvaluationEngineError
from harass.application.evaluation.outcome_codec import read_outcome
from harass.application.ports.evaluation import EvaluationJournal
from harass.application.ports.runs import LeaseLostError, RunJob
from harass.application.reporting.document import outcome_document
from harass.domain.case_outcome import CaseOutcome
from harass.infrastructure.persistence.job_sessions import job_session, owned_job
from harass.infrastructure.persistence.session_factory import SessionFactory
from harass.infrastructure.persistence.tables import RunJobRow, RunOutcomeRow, RunRow
from harass.infrastructure.persistence.upsert import insert_for

# Metric reads never need request or response text, so it stays out of them.
TEXT_FREE_FIELDS = {
    "original_prompt": "Stored request",
    "objective": "Stored request",
    "transcript": None,
    "judge_requests": (),
}


class SqlAlchemyEvaluationJournal(EvaluationJournal):
    """Recover progress without repeating uncertain submissions."""

    def __init__(self, factory: SessionFactory, job: RunJob, clock: Callable[[], datetime]) -> None:
        """Bind journal operations to the leased run."""
        self._factory = factory
        self._job = job
        self._clock = clock
        self._revision: int | None = None
        self._case_index = 0

    def initialize(self, fingerprint: str, total_cases: int) -> dict[str, Any]:
        """Reject changed cases or execution parameters when resuming."""
        with job_session(self._factory) as session:
            row = owned_job(session, self._job, self._clock())
            if row.plan_fingerprint not in {None, fingerprint}:
                raise EvaluationEngineError("Evaluation inputs changed after checkpoint creation.")
            row.plan_fingerprint = fingerprint
            run = session.get(RunRow, row.run_id)
            if run is None:
                raise LeaseLostError("The run no longer exists.")
            run.total_cases = total_cases
            self._revision = row.revision
            self._case_index = row.checkpoint.get("case_index", 0)
            return row.checkpoint

    def reserve(self, checkpoint: dict[str, Any]) -> None:
        """Persist submission intent before contacting the target."""
        self._save(checkpoint)

    def commit(self, outcome: CaseOutcome, checkpoint: dict[str, Any]) -> None:
        """Commit evidence and progress atomically."""
        self._save(checkpoint, outcome)

    def _save(self, checkpoint: dict[str, Any], outcome: CaseOutcome | None = None) -> None:
        """Commit a checkpoint and optional evidence under the lease."""
        if self._revision is None:
            raise EvaluationEngineError("The journal must be initialized before writes.")
        with job_session(self._factory) as session:
            row = owned_job(session, self._job, self._clock())
            if row.revision != self._revision:
                raise LeaseLostError("The checkpoint was already advanced by another writer.")
            changed = session.scalar(
                update(RunJobRow)
                .where(
                    RunJobRow.run_id == row.run_id,
                    RunJobRow.worker_id == self._job.worker_id,
                    RunJobRow.revision == self._revision,
                )
                .values(checkpoint=checkpoint, revision=self._revision + 1)
                .returning(RunJobRow.run_id)
            )
            if changed is None:
                raise LeaseLostError("The checkpoint was concurrently advanced.")
            run = session.get(RunRow, row.run_id)
            if run is None:
                raise LeaseLostError("The run no longer exists.")
            run.completed_cases = checkpoint["case_index"]
            if outcome is not None:
                self._record(session, run, outcome)
        self._revision += 1
        self._case_index = checkpoint["case_index"]

    def _record(self, session: Session, run: RunRow, outcome: CaseOutcome) -> None:
        """Store one attempt once, with a text-free copy for metrics."""
        document = outcome_document(outcome)
        metric = {**document, **TEXT_FREE_FIELDS}
        session.execute(
            insert_for(session, RunOutcomeRow)
            .values(
                run_id=run.run_id,
                case_index=self._case_index,
                document=document,
                metric_document=metric,
            )
            .on_conflict_do_nothing(index_elements=["run_id", "case_index"])
        )

    def outcomes(self, *, lightweight: bool = False) -> Iterator[CaseOutcome]:
        """Read at most 100 stored attempt documents into memory at a time."""
        for document in stored_documents(
            self._factory, self._job.run.run_id, lightweight=lightweight
        ):
            yield read_outcome(document, lightweight=lightweight)


def stored_documents(
    factory: SessionFactory, run_id: str, *, lightweight: bool = False
) -> Iterator[dict[str, Any]]:
    """Export evidence with keyset pagination and bounded database sessions."""
    last_case = -1
    while True:
        with job_session(factory) as session:
            column = RunOutcomeRow.metric_document if lightweight else RunOutcomeRow.document
            rows = list(
                session.execute(
                    select(RunOutcomeRow.case_index, column)
                    .where(RunOutcomeRow.run_id == run_id, RunOutcomeRow.case_index > last_case)
                    .order_by(RunOutcomeRow.case_index)
                    .limit(100)
                )
            )
        if not rows:
            return
        for case_index, document in rows:
            last_case = case_index
            yield document
