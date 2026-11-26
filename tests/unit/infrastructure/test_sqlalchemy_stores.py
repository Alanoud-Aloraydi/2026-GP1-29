"""Tests for the SQLAlchemy connection and run stores and the finding archive."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from harass.application.errors import ConflictError, UnknownConnectionError, UnknownRunError
from harass.domain.evaluation_run import EvaluationRun, RunStatus
from harass.domain.model_connection import ConnectionStatus, ModelConnection
from harass.infrastructure.persistence.prompt_archive import archive_findings
from harass.infrastructure.persistence.row_mapping import new_run_row
from harass.infrastructure.persistence.sqlalchemy_connections import SqlAlchemyConnectionStore
from harass.infrastructure.persistence.sqlalchemy_runs import SqlAlchemyRunStore
from harass.infrastructure.persistence.tables import (
    Base,
    GeneratedPromptRow,
    PromptFindingRow,
    ReportRow,
    RunRow,
)

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


def archive(factory: sessionmaker[Session], run_id: str, document: dict[str, Any]) -> None:
    """Archive the findings of a report in one transaction, as the journal does."""
    with factory() as session, session.begin():
        row = session.get(RunRow, run_id)
        assert row is not None
        archive_findings(session, row, document)


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


def generated_outcome(text: str = "generated request") -> dict[str, Any]:
    """Return a scored generated defect with its research provenance."""
    return {
        "case_id": "case-1",
        "axis": "AT",
        "variant_name": "recipe-1",
        "attempt_number": 1,
        "original_prompt": "human seed",
        "error": None,
        "response_category": "FUL",
        "attack_succeeded": True,
        "variant": {"template_name": "shell", "transform_names": []},
        "transcript": {"sent_prompt": text, "response": "synthetic response"},
    }


def test_archive_deduplicates_text_but_retains_independent_observations(
    session_factory: sessionmaker[Session],
) -> None:
    """Replayed delivery is idempotent; another run retains another finding."""
    document = {"outcomes": [generated_outcome()], "target_endpoint": "https://api.invalid/v1"}
    # An owner holds one active run at a time, so the first one has finished.
    store_runs(session_factory, replace(run(), status=RunStatus.COMPLETED), run("run-2"))
    for run_id in ("run-1", "run-1", "run-2"):
        archive(session_factory, run_id, document)
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(GeneratedPromptRow)) == 1
        assert session.scalar(select(func.count()).select_from(PromptFindingRow)) == 2
        finding = session.scalars(select(PromptFindingRow)).first()
        assert finding is not None
        assert finding.evidence["label_source"] == "automated_judge"
        assert finding.target_endpoint == document["target_endpoint"]


@pytest.mark.parametrize(
    "changes",
    [
        {"variant_name": "baseline"},
        {"error": "timeout"},
        {"attack_succeeded": False},
        {"response_category": None},
        {"axis": "OR", "response_category": "UNC"},
        {"axis": "OR", "response_category": "FUL"},
        {"variant": None},
        {"transcript": None},
    ],
)
def test_archive_excludes_originals_failed_and_unscored_attempts(
    session_factory: sessionmaker[Session], changes: dict[str, Any]
) -> None:
    """Only scored defects of generated attempts become findings."""
    store_runs(session_factory, run())
    archive(session_factory, "run-1", {"outcomes": [{**generated_outcome(), **changes}]})
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PromptFindingRow)) == 0


def test_archive_preserves_invisible_characters_and_over_refusal_findings(
    session_factory: sessionmaker[Session],
) -> None:
    """Surface differences remain distinct even when they look alike."""
    store_runs(session_factory, run())
    first = generated_outcome("request")
    second = {
        **generated_outcome("re​quest"),
        "variant_name": "recipe-2",
        "axis": "OR",
        "response_category": "REF",
        "attack_succeeded": None,
    }
    archive(session_factory, "run-1", {"outcomes": [first, second]})
    with session_factory() as session:
        assert set(session.scalars(select(GeneratedPromptRow.text))) == {"request", "re​quest"}
        assert session.scalar(select(func.count()).select_from(PromptFindingRow)) == 2


def test_concurrent_delivery_archives_one_observation(tmp_path: Path) -> None:
    """Concurrent writers of the same finding store it once."""
    engine = create_engine(f"sqlite:///{tmp_path / 'archive.sqlite'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    store_runs(factory, run())
    document = {"outcomes": [generated_outcome()], "target_model": "executed-model"}
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: archive(factory, "run-1", document), range(8)))
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(PromptFindingRow)) == 1
        assert session.scalars(select(PromptFindingRow)).one().target_model == "executed-model"
    engine.dispose()


def test_archive_failure_rolls_back_prior_findings(session_factory: sessionmaker[Session]) -> None:
    """A malformed finding cannot leave a partially saved archive."""
    store_runs(session_factory, run())
    document = {
        "outcomes": [
            generated_outcome(),
            {**generated_outcome(), "transcript": {"response": "missing sent prompt"}},
        ]
    }
    with pytest.raises(KeyError):
        archive(session_factory, "run-1", document)
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(GeneratedPromptRow)) == 0
        assert session.scalar(select(func.count()).select_from(PromptFindingRow)) == 0
