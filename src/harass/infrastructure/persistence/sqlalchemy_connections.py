"""Persist owned model connections and encrypted credentials."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from harass.application.errors import (
    ConflictError,
    UnknownConnectionError,
)
from harass.application.ports.connection_store import ConnectionStore
from harass.domain.model_connection import ConnectionStatus, ModelConnection
from harass.infrastructure.persistence.row_mapping import utc_timestamp
from harass.infrastructure.persistence.session_factory import SessionFactory
from harass.infrastructure.persistence.tables import (
    ConnectionRow,
    RunRow,
)


class SqlAlchemyConnectionStore(ConnectionStore):
    """Stores connections and their encrypted keys in a relational database."""

    def __init__(self, session_factory: SessionFactory) -> None:
        """Store the session factory used for each operation."""
        self._session_factory = session_factory

    def save(
        self, connection: ModelConnection, encrypted_api_key: str | None
    ) -> None:
        """Save a connection while retaining an omitted API key."""
        with self._session_factory() as session, session.begin():
            row = session.get(
                ConnectionRow, connection.connection_id, with_for_update=True
            )
            if row is None:
                if encrypted_api_key is None:
                    raise UnknownConnectionError(connection.connection_id)
                session.add(_connection_row(connection, encrypted_api_key))
                return
            if (
                row.owner_id != connection.owner_id
                or row.revision != connection.revision
            ):
                raise ConflictError(
                    "Connection changed; reload before verifying "
                    "or editing it."
                )
            active = session.scalar(
                select(RunRow.run_id)
                .where(
                    RunRow.connection_id == row.connection_id,
                    (RunRow.status.in_(["pending", "running"]))
                    | RunRow.resumable,
                )
                .limit(1)
            )
            if active:
                raise ConflictError(
                    "This connection belongs to an active evaluation."
                )
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
            return self._row(
                session, connection_id, owner_id
            ).encrypted_api_key

    def snapshot(
        self, connection_id: str, owner_id: str
    ) -> tuple[ModelConnection, str]:
        """Read metadata and encrypted credentials from one row version."""
        with self._session_factory() as session:
            row = self._row(session, connection_id, owner_id)
            return _connection(row), row.encrypted_api_key

    def page_for_owner(
        self, owner_id: str, offset: int, limit: int
    ) -> list[ModelConnection]:
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

    def _row(
        self, session: Session, connection_id: str, owner_id: str
    ) -> ConnectionRow:
        """Return the row owned by ``owner_id`` or raise."""
        row = session.get(ConnectionRow, connection_id)
        if row is None or row.owner_id != owner_id:
            raise UnknownConnectionError(connection_id)
        return row


def _connection_row(
    connection: ModelConnection, encrypted_api_key: str
) -> ConnectionRow:
    """Build a new connection row."""
    row = ConnectionRow(
        connection_id=connection.connection_id,
        encrypted_api_key=encrypted_api_key,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    _update_connection_row(row, connection)
    return row


def _update_connection_row(
    row: ConnectionRow, connection: ModelConnection
) -> None:
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
        last_tested_at=utc_timestamp(row.last_tested_at),
        revision=row.revision,
        created_at=utc_timestamp(row.created_at),
        updated_at=utc_timestamp(row.updated_at),
    )
