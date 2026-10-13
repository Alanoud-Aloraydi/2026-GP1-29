"""Per-attempt evidence and checkpoints committed under a fenced worker lease."""

from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

from sqlalchemy import select, update

from harass.application.errors import EvaluationEngineError
from harass.application.outcome_codec import read_outcome
from harass.application.ports.evaluation_journal import EvaluationJournal
from harass.application.ports.run_queue import LeaseLostError, RunJob
from harass.application.report_document import outcome_document
from harass.domain.case_outcome import CaseOutcome
from harass.infrastructure.persistence.job_sessions import job_session, owned_job
from harass.infrastructure.persistence.prompt_archive import archive_findings
from harass.infrastructure.persistence.sqlalchemy_stores import SessionFactory
from harass.infrastructure.persistence.tables import RunJobRow, RunOutcomeRow, RunRow
from harass.infrastructure.persistence.upsert import insert_for


class SqlAlchemyEvaluationJournal(EvaluationJournal):
    """Recover persisted progress without resubmitting ambiguous external requests."""

    def __init__(
        self, factory: SessionFactory, job: RunJob, clock: Callable[[], datetime]
    ) -> None:
        """Bind journal operations to the leased run."""
        self._factory, self._job, self._clock = factory, job, clock
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
        """Persist the submission intent before any target request can begin."""
        self._save(checkpoint)

    def commit(self, outcome: CaseOutcome, checkpoint: dict[str, Any]) -> None:
        """Commit evidence, research findings, progress and controller feedback together."""
        self._save(checkpoint, outcome)

    def _save(self, checkpoint: dict[str, Any], outcome: CaseOutcome | None = None) -> None:
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
                document = outcome_document(outcome)
                metric = {
                    **document,
                    "original_prompt": "Stored request",
                    "objective": "Stored request",
                    "variant": None,
                    "transcript": None,
                    "judge_requests": (),
                }
                session.execute(
                    insert_for(session, RunOutcomeRow)
                    .values(
                        run_id=row.run_id,
                        case_index=self._case_index,
                        attempt_number=outcome.attempt_number,
                        document=document,
                        metric_document=metric,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["run_id", "case_index", "attempt_number"]
                    )
                )
                run.completed_attempts += 1
                archive_findings(
                    session,
                    run,
                    {
                        "outcomes": [document],
                        "target_model": run.target_model,
                        "target_endpoint": self._job.target_endpoint,
                    },
                )
        self._revision += 1
        self._case_index = checkpoint["case_index"]

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
    last_case, last_attempt = -1, -1
    while True:
        with job_session(factory) as session:
            column = RunOutcomeRow.metric_document if lightweight else RunOutcomeRow.document
            rows = list(
                session.execute(
                    select(
                        RunOutcomeRow.case_index,
                        RunOutcomeRow.attempt_number,
                        column,
                    )
                    .where(
                        RunOutcomeRow.run_id == run_id,
                        (RunOutcomeRow.case_index > last_case)
                        | (
                            (RunOutcomeRow.case_index == last_case)
                            & (RunOutcomeRow.attempt_number > last_attempt)
                        ),
                    )
                    .order_by(RunOutcomeRow.case_index, RunOutcomeRow.attempt_number)
                    .limit(100)
                )
            )
        if not rows:
            return
        for case_index, attempt_number, document in rows:
            last_case, last_attempt = case_index, attempt_number
            yield document
