"""Tests for the SQLAlchemy connection and run stores."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from harass.application.errors import ConflictError, UnknownConnectionError, UnknownRunError
from harass.domain.evaluation_run import EvaluationRun, RunStatus
from harass.domain.model_connection import ConnectionStatus, ModelConnection
from harass.infrastructure.persistence.row_mapping import new_run_row
from harass.infrastructure.persistence.sqlalchemy_connections import SqlAlchemyConnectionStore
from harass.infrastructure.persistence.sqlalchemy_runs import SqlAlchemyRunStore
from harass.infrastructure.persistence.tables import Base, ReportRow

NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    """Return a session factory bound to a fresh in-memory database."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield sessionmaker(engine)
    engine.dispose()


def connection(
    owner: str = "user-1", status: ConnectionStatus = ConnectionStatus.NOT_TESTED
) -> ModelConnection:
    """Return a connection for the given owner and status."""
    return ModelConnection(
        connection_id="conn-1",
        owner_id=owner,
        base_url="https://api.invalid/v1",
        model_name="model",
        status=status,
    )


def test_connection_round_trip_and_key_update(session_factory: sessionmaker[Session]) -> None:
    """Saving then updating keeps or replaces the encrypted key as asked."""
    store = SqlAlchemyConnectionStore(session_factory)
    store.save(connection(), "enc-1")
    store.save(connection(status=ConnectionStatus.CONNECTED), None)

    saved, key = store.snapshot("conn-1", "user-1")
    assert saved.status is ConnectionStatus.CONNECTED
    assert key == "enc-1"


def test_connection_is_scoped_to_its_owner(session_factory: sessionmaker[Session]) -> None:
    """Another owner cannot read the connection."""
    store = SqlAlchemyConnectionStore(session_factory)
    store.save(connection(), "enc-1")

    with pytest.raises(UnknownConnectionError):
        store.get("conn-1", "user-2")


def test_saving_without_a_key_for_a_new_connection_fails(
    session_factory: sessionmaker[Session],
) -> None:
    """A brand-new connection must bring its key."""
    store = SqlAlchemyConnectionStore(session_factory)

    with pytest.raises(UnknownConnectionError):
        store.save(connection(), None)


def test_snapshot_rejects_stale_verification_and_keeps_matching_key(
    session_factory: sessionmaker[Session],
) -> None:
    """Verification cannot overwrite a newer endpoint/key snapshot."""
    store = SqlAlchemyConnectionStore(session_factory)
    store.save(connection(), "first-key")
    original, original_key = store.snapshot("conn-1", "user-1")
    store.save(replace(original, model_name="new-model"), "second-key")
    with pytest.raises(ConflictError):
        store.save(replace(original, status=ConnectionStatus.CONNECTED), None)
    latest, latest_key = store.snapshot("conn-1", "user-1")
    assert original_key == "first-key" and latest_key == "second-key"
    assert latest.model_name == "new-model" and latest.revision == original.revision + 1
    assert latest.created_at is not None and latest.created_at.tzinfo is UTC


def run(run_id: str = "run-1", owner: str = "user-1", created: datetime = NOW) -> EvaluationRun:
    """Return a pending run."""
    return EvaluationRun(
        run_id=run_id,
        owner_id=owner,
        connection_id="conn-1",
        target_model="model",
        status=RunStatus.PENDING,
        created_at=created,
    )


def store_runs(factory: sessionmaker[Session], *runs: EvaluationRun) -> None:
    """Insert runs as the queue admits them."""
    with factory() as session, session.begin():
        session.add_all(new_run_row(item) for item in runs)


def test_stored_report_is_read_by_its_owner_only(session_factory: sessionmaker[Session]) -> None:
    """A run's report is returned to its owner; another owner sees nothing."""
    store_runs(session_factory, run())
    with session_factory() as session, session.begin():
        session.add(ReportRow(run_id="run-1", document={"run_identifier": "run-1"}))
    store = SqlAlchemyRunStore(session_factory)

    assert store.get_report("run-1", "user-1")["run_identifier"] == "run-1"
    with pytest.raises(UnknownRunError):
        store.get_report("run-1", "user-2")


def test_runs_are_paged_most_recent_first(session_factory: sessionmaker[Session]) -> None:
    """History pages order by creation time, newest first, and count statuses."""
    old = replace(run("run-old"), status=RunStatus.COMPLETED)
    store_runs(session_factory, old, run("run-new", created=datetime(2026, 2, 1, tzinfo=UTC)))
    store = SqlAlchemyRunStore(session_factory)

    assert [r.run_id for r in store.page_for_owner("user-1", 0, 10)] == ["run-new", "run-old"]
    assert store.counts_for_owner("user-1") == {"pending": 1, "completed": 1}


def test_missing_report_is_reported(session_factory: sessionmaker[Session]) -> None:
    """A run without a stored report raises when its report is requested."""
    store_runs(session_factory, run())

    with pytest.raises(UnknownRunError):
        SqlAlchemyRunStore(session_factory).get_report("run-1", "user-1")


def test_sqlite_run_timestamps_retain_utc(session_factory: sessionmaker[Session]) -> None:
    """SQLite drops time zones; reading a run restores UTC."""
    store_runs(session_factory, run())

    restored = SqlAlchemyRunStore(session_factory).get("run-1", "user-1")
    assert restored.created_at == NOW and restored.created_at.tzinfo is UTC
