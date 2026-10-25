"""Query evaluation histories and persist report documents."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from harass.application.errors import (
    UnknownRunError,
)
from harass.application.ports.run_store import RunStore
from harass.domain.evaluation_run import EvaluationRun
from harass.infrastructure.persistence.prompt_archive import archive_findings
from harass.infrastructure.persistence.row_mapping import new_run_row, read_run
from harass.infrastructure.persistence.session_factory import SessionFactory
from harass.infrastructure.persistence.tables import (
    ReportRow,
    RunRow,
)
from harass.infrastructure.persistence.upsert import insert_for


class SqlAlchemyRunStore(RunStore):
    """Stores runs and their report documents in a relational database."""

    def __init__(self, session_factory: SessionFactory) -> None:
        """Store the session factory used for each operation."""
        self._session_factory = session_factory

    def create(self, run: EvaluationRun) -> None:
        """Insert a new run."""
        with self._session_factory() as session, session.begin():
            session.add(new_run_row(run))

    def update(self, run: EvaluationRun) -> None:
        """Replace the stored lifecycle fields of an existing run."""
        with self._session_factory() as session, session.begin():
            row = self._row(session, run.run_id, run.owner_id)
            row.status = run.status.value
            row.target_model = run.target_model
            row.finished_at = run.finished_at
            row.error = run.error

    def save_report(self, run_id: str, document: dict[str, Any]) -> None:
        """Store the serialized report document of a completed run."""
        with self._session_factory() as session, session.begin():
            run = session.get(RunRow, run_id)
            if run is None:
                raise UnknownRunError(run_id)
            session.execute(
                insert_for(session, ReportRow)
                .values(run_id=run_id, document=document)
                .on_conflict_do_update(
                    index_elements=["run_id"], set_={"document": document}
                )
            )
            if "outcomes" in document:
                archive_findings(session, run, document)

    def get(self, run_id: str, owner_id: str) -> EvaluationRun:
        """Return the owner's runs, most recent first."""
        with self._session_factory() as session:
            return read_run(self._row(session, run_id, owner_id))

    def get_report(self, run_id: str, owner_id: str) -> dict[str, Any]:
        """Return the stored report document of the owner's completed run."""
        with self._session_factory() as session:
            self._row(session, run_id, owner_id)
            report = session.get(ReportRow, run_id)
            if report is None:
                raise UnknownRunError(f"Run {run_id} has no stored report.")
            return report.document

    def list_for_owner(self, owner_id: str) -> list[EvaluationRun]:
        """Return the owner's runs, most recent first."""
        with self._session_factory() as session:
            rows = session.scalars(
                select(RunRow)
                .where(RunRow.owner_id == owner_id)
                .order_by(RunRow.created_at.desc(), RunRow.run_id)
            )
            return [read_run(row) for row in rows]

    def _row(self, session: Session, run_id: str, owner_id: str) -> RunRow:
        """Return the run owned by ``owner_id`` or raise."""
        row = session.get(RunRow, run_id)
        if row is None or row.owner_id != owner_id:
            raise UnknownRunError(run_id)
        return row

    def page_for_owner(
        self, owner_id: str, offset: int, limit: int
    ) -> list[EvaluationRun]:
        """Load only one history page in a stable order."""
        with self._session_factory() as session:
            return [
                read_run(row)
                for row in session.scalars(
                    select(RunRow)
                    .where(RunRow.owner_id == owner_id)
                    .order_by(RunRow.created_at.desc(), RunRow.run_id)
                    .offset(offset)
                    .limit(limit)
                )
            ]

    def counts_for_owner(self, owner_id: str) -> dict[str, int]:
        """Aggregate lifecycle counts without loading report evidence."""
        with self._session_factory() as session:
            return dict(
                session.execute(
                    select(RunRow.status, func.count())
                    .where(RunRow.owner_id == owner_id)
                    .group_by(RunRow.status)
                ).all()
            )
