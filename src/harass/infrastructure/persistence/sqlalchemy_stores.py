"""SQLAlchemy-backed implementations of the connection and run stores."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from harass.application.errors import ConflictError, UnknownConnectionError, UnknownRunError
from harass.application.ports.connection_store import ConnectionStore
from harass.application.ports.run_store import RunStore
from harass.domain.evaluation_run import EvaluationRun, RunStatus
from harass.domain.model_connection import ConnectionStatus, ModelConnection
from harass.infrastructure.persistence.prompt_archive import archive_findings
from harass.infrastructure.persistence.tables import ConnectionRow, ReportRow, RunRow
from harass.infrastructure.persistence.upsert import insert_for

type SessionFactory = Callable[[], Session]


class SqlAlchemyConnectionStore(ConnectionStore):
    """Stores connections and their encrypted keys in a relational database."""

    def __init__(self, session_factory: SessionFactory) -> None:
        """Store the session factory used for each operation."""
        self._session_factory = session_factory

    def save(self, connection: ModelConnection, encrypted_api_key: str | None) -> None:
        """Insert or update a connection; ``None`` keeps the stored key unchanged."""
        with self._session_factory() as session, session.begin():
            row = session.get(ConnectionRow, connection.connection_id, with_for_update=True)
            if row is None:
                if encrypted_api_key is None:
                    raise UnknownConnectionError(connection.connection_id)
                session.add(_connection_row(connection, encrypted_api_key))
                return
            if row.owner_id != connection.owner_id or row.revision != connection.revision:
                raise ConflictError("Connection changed; reload before verifying or editing it.")
            active = session.scalar(
                select(RunRow.run_id)
                .where(
                    RunRow.connection_id == row.connection_id,
                    (RunRow.status.in_(["pending", "running"])) | RunRow.resumable,
                )
                .limit(1)
            )
            if active:
                raise ConflictError("This connection belongs to an active evaluation.")
            _update_connection_row(row, connection)
            row.revision += 1
            row.updated_at = datetime.now(UTC)
            if encrypted_api_key is not None:
                row.encrypted_api_key = encrypted_api_key

    def get(self, connection_id: str, owner_id: str) -> ModelConnection:
        """Return the owner's connection or raise."""
        with self._session_factory() as session:
            return _connection(self._row(session, connection_id, owner_id))

    def list_for_owner(self, owner_id: str) -> list[ModelConnection]:
        """Return the owner's connections ordered by identifier."""
        with self._session_factory() as session:
            rows = session.scalars(
                select(ConnectionRow)
                .where(ConnectionRow.owner_id == owner_id)
                .order_by(ConnectionRow.connection_id)
            )
            return [_connection(row) for row in rows]

    def encrypted_api_key(self, connection_id: str, owner_id: str) -> str:
        """Return the stored encrypted key of the owner's connection."""
        with self._session_factory() as session:
            return self._row(session, connection_id, owner_id).encrypted_api_key

    def snapshot(self, connection_id: str, owner_id: str) -> tuple[ModelConnection, str]:
        """Read endpoint, model, revision and encrypted key from the same row version."""
        with self._session_factory() as session:
            row = self._row(session, connection_id, owner_id)
            return _connection(row), row.encrypted_api_key

    def page_for_owner(self, owner_id: str, offset: int, limit: int) -> list[ModelConnection]:
        """Load only one connection page."""
        with self._session_factory() as session:
            return [
                _connection(row)
                for row in session.scalars(
                    select(ConnectionRow)
                    .where(ConnectionRow.owner_id == owner_id)
                    .order_by(ConnectionRow.connection_id)
                    .offset(offset)
                    .limit(limit)
                )
            ]

    def counts_for_owner(self, owner_id: str) -> dict[str, int]:
        """Aggregate connection status counts within this account."""
        with self._session_factory() as session:
            return dict(
                session.execute(
                    select(ConnectionRow.status, func.count())
                    .where(ConnectionRow.owner_id == owner_id)
                    .group_by(ConnectionRow.status)
                ).all()
            )

    def _row(self, session: Session, connection_id: str, owner_id: str) -> ConnectionRow:
        """Return the row owned by ``owner_id`` or raise."""
        row = session.get(ConnectionRow, connection_id)
        if row is None or row.owner_id != owner_id:
            raise UnknownConnectionError(connection_id)
        return row


class SqlAlchemyRunStore(RunStore):
    """Stores runs and their report documents in a relational database."""

    def __init__(self, session_factory: SessionFactory) -> None:
        """Store the session factory used for each operation."""
        self._session_factory = session_factory

    def create(self, run: EvaluationRun) -> None:
        """Insert a new run."""
        with self._session_factory() as session, session.begin():
            session.add(_run_row(run))

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
                .on_conflict_do_update(index_elements=["run_id"], set_={"document": document})
            )
            if "outcomes" in document:
                archive_findings(session, run, document)

    def get(self, run_id: str, owner_id: str) -> EvaluationRun:
        """Return the owner's run."""
        with self._session_factory() as session:
            return _run(self._row(session, run_id, owner_id))

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
            return [_run(row) for row in rows]

    def _row(self, session: Session, run_id: str, owner_id: str) -> RunRow:
        """Return the run owned by ``owner_id`` or raise."""
        row = session.get(RunRow, run_id)
        if row is None or row.owner_id != owner_id:
            raise UnknownRunError(run_id)
        return row

    def page_for_owner(self, owner_id: str, offset: int, limit: int) -> list[EvaluationRun]:
        """Load only one history page in a stable order."""
        with self._session_factory() as session:
            return [
                _run(row)
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


def _connection_row(connection: ModelConnection, encrypted_api_key: str) -> ConnectionRow:
    """Build a new connection row."""
    row = ConnectionRow(
        connection_id=connection.connection_id,
        encrypted_api_key=encrypted_api_key,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    _update_connection_row(row, connection)
    return row


def _update_connection_row(row: ConnectionRow, connection: ModelConnection) -> None:
    """Copy the mutable connection fields onto a row."""
    row.owner_id = connection.owner_id
    row.base_url = connection.base_url
    row.model_name = connection.model_name
    row.status = connection.status.value
    row.failure_reason = connection.failure_reason
    row.last_tested_at = connection.last_tested_at


def _connection(row: ConnectionRow) -> ModelConnection:
    """Rebuild a domain connection from a row."""
    return ModelConnection(
        connection_id=row.connection_id,
        owner_id=row.owner_id,
        base_url=row.base_url,
        model_name=row.model_name,
        status=ConnectionStatus(row.status),
        failure_reason=row.failure_reason,
        last_tested_at=_utc(row.last_tested_at),
        revision=row.revision,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


def _run_row(run: EvaluationRun) -> RunRow:
    """Build a new run row."""
    return RunRow(
        run_id=run.run_id,
        owner_id=run.owner_id,
        connection_id=run.connection_id,
        target_model=run.target_model,
        status=run.status.value,
        created_at=run.created_at,
        lifecycle_events=[{"event": "created", "at": run.created_at.isoformat()}],
        finished_at=run.finished_at,
        error=run.error,
    )


def _run(row: RunRow) -> EvaluationRun:
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
        finished_at=_utc(row.finished_at),
        error=row.error,
        total_cases=row.total_cases,
        completed_cases=row.completed_cases,
        completed_attempts=row.completed_attempts,
        resumable=row.resumable,
        started_at=_utc(row.started_at),
        lifecycle_events=tuple(row.lifecycle_events or ()),
    )


def _utc(value: datetime | None) -> datetime | None:
    """Restore UTC metadata when SQLite returns timezone-naive timestamps."""
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value
