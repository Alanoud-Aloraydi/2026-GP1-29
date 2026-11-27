"""Read evaluation histories and their report documents."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from harass.application.errors import UnknownRunError
from harass.application.evaluation.contracts import RunParameters
from harass.application.ports.runs import RunStore
from harass.domain.evaluation_run import ACTIVE_STATUSES, EvaluationRun, RunKind, RunStatus
from harass.domain.taxonomy import Axis
from harass.infrastructure.persistence.row_mapping import read_run
from harass.infrastructure.persistence.session_factory import SessionFactory
from harass.infrastructure.persistence.tables import ReportRow, RunJobRow, RunRow


class SqlAlchemyRunStore(RunStore):
    """Reads runs and their report documents from a relational database."""

    def __init__(self, factory: SessionFactory) -> None:
        """Store the session factory used for each operation."""
        self._factory = factory

    def get(self, run_id: str, owner_id: str) -> EvaluationRun:
        """Return one run of the owner."""
        with self._factory() as session:
            return read_run(_owned(session, run_id, owner_id))

    def get_report(self, run_id: str, owner_id: str) -> dict[str, Any]:
        """Return the stored report document of the owner's completed run."""
        with self._factory() as session:
            _owned(session, run_id, owner_id)
            report = session.get(ReportRow, run_id)
            if report is None:
                raise UnknownRunError(f"Run {run_id} has no stored report.")
            return report.document

    def page_for_owner(self, owner_id: str, offset: int, limit: int) -> list[EvaluationRun]:
        """Load only one history page in a stable order."""
        with self._factory() as session:
            rows = session.scalars(
                select(RunRow)
                .where(RunRow.owner_id == owner_id)
                .order_by(RunRow.created_at.desc(), RunRow.run_id)
                .offset(offset)
                .limit(limit)
            )
            return [read_run(row) for row in rows]

    def counts_for_owner(self, owner_id: str) -> dict[str, int]:
        """Aggregate lifecycle counts without loading report evidence."""
        with self._factory() as session:
            counts = session.execute(
                select(RunRow.status, func.count())
                .where(RunRow.owner_id == owner_id)
                .group_by(RunRow.status)
            )
            return {status: count for status, count in counts}

    def baselines(
        self, owner_id: str, connection_id: str
    ) -> list[tuple[EvaluationRun, Axis | None]]:
        """Return the baseline runs that completed or may still complete, newest first.

        O(n) in the connection's baseline runs, each read with its job inputs.
        """
        with self._factory() as session:
            rows = session.execute(
                select(RunRow, RunJobRow.parameters)
                .join(RunJobRow, RunJobRow.run_id == RunRow.run_id)
                .where(
                    RunRow.owner_id == owner_id,
                    RunRow.connection_id == connection_id,
                    RunRow.kind == RunKind.BASELINE,
                    RunRow.status.in_((RunStatus.COMPLETED, *ACTIVE_STATUSES)) | RunRow.resumable,
                )
                .order_by(RunRow.created_at.desc(), RunRow.run_id)
            )
            return [
                (read_run(row), RunParameters.from_document(parameters).selection.axis)
                for row, parameters in rows
            ]


def _owned(session: Session, run_id: str, owner_id: str) -> RunRow:
    """Return the run owned by ``owner_id``; another owner's run counts as unknown."""
    row = session.get(RunRow, run_id)
    if row is None or row.owner_id != owner_id:
        raise UnknownRunError(run_id)
    return row
