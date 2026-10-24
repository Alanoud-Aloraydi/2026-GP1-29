"""Tests for the SQLAlchemy connection and run stores on in-memory SQLite."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from harass.application.errors import UnknownConnectionError, UnknownRunError
from harass.domain.evaluation_run import EvaluationRun, RunStatus
from harass.domain.model_connection import ConnectionStatus, ModelConnection
from harass.infrastructure.persistence.sqlalchemy_connections import (
    SqlAlchemyConnectionStore,
)
from harass.infrastructure.persistence.sqlalchemy_runs import (
    SqlAlchemyRunStore,
)
from harass.infrastructure.persistence.tables import (
    Base,
    GeneratedPromptRow,
    PromptFindingRow,
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
    owner: str = "user-1",
    status: ConnectionStatus = ConnectionStatus.NOT_TESTED,
) -> ModelConnection:
    """Return a connection for the given owner and status."""
    return ModelConnection(
        connection_id="conn-1",
        owner_id=owner,
        base_url="https://api.invalid/v1",
        model_name="model",
        status=status,
    )


def test_connection_round_trip_and_key_update(
    session_factory: sessionmaker[Session],
) -> None:
    """Saving then updating keeps or replaces the encrypted key as asked."""
    store = SqlAlchemyConnectionStore(session_factory)
    store.save(connection(), "enc-1")
    store.save(connection(status=ConnectionStatus.CONNECTED), None)

    assert store.get("conn-1", "user-1").status is ConnectionStatus.CONNECTED
    assert store.encrypted_api_key("conn-1", "user-1") == "enc-1"


def test_connection_is_scoped_to_its_owner(
    session_factory: sessionmaker[Session],
) -> None:
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


def run(
    run_id: str = "run-1", owner: str = "user-1", created: datetime = NOW
) -> EvaluationRun:
    """Return a pending run."""
    return EvaluationRun(
        run_id=run_id,
        owner_id=owner,
        connection_id="conn-1",
        target_model="model",
        status=RunStatus.PENDING,
        created_at=created,
    )


def test_run_lifecycle_and_report(
    session_factory: sessionmaker[Session],
) -> None:
    """A run can be created, advanced and given a report."""
    store = SqlAlchemyRunStore(session_factory)
    store.create(run())
    store.update(
        EvaluationRun(
            run_id="run-1",
            owner_id="user-1",
            connection_id="conn-1",
            target_model="model",
            status=RunStatus.COMPLETED,
            created_at=NOW,
            finished_at=NOW,
        )
    )
    store.save_report("run-1", {"run_identifier": "run-1", "metrics": {}})

    assert store.get("run-1", "user-1").status is RunStatus.COMPLETED
    assert store.get_report("run-1", "user-1")["run_identifier"] == "run-1"


def test_runs_are_listed_most_recent_first(
    session_factory: sessionmaker[Session],
) -> None:
    """Listing orders by creation time, newest first."""
    store = SqlAlchemyRunStore(session_factory)
    store.create(
        replace(
            run("run-old", created=datetime(2026, 1, 1, tzinfo=UTC)),
            status=RunStatus.COMPLETED,
        )
    )
    store.create(run("run-new", created=datetime(2026, 2, 1, tzinfo=UTC)))

    assert [r.run_id for r in store.list_for_owner("user-1")] == [
        "run-new",
        "run-old",
    ]


def test_missing_report_is_reported(
    session_factory: sessionmaker[Session],
) -> None:
    """A run without a stored report raises when its report is requested."""
    store = SqlAlchemyRunStore(session_factory)
    store.create(run())

    with pytest.raises(UnknownRunError):
        store.get_report("run-1", "user-1")


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
    store = SqlAlchemyRunStore(session_factory)
    document = {
        "outcomes": [generated_outcome()],
        "target_endpoint": "https://api.invalid/v1",
    }
    store.create(replace(run(), status=RunStatus.COMPLETED))
    store.create(run("run-2"))
    store.save_report("run-1", document)
    store.save_report("run-1", document)
    store.save_report("run-2", document)
    with session_factory() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(GeneratedPromptRow)
            )
            == 1
        )
        assert (
            session.scalar(select(func.count()).select_from(PromptFindingRow))
            == 2
        )
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
    """Verify archive excludes originals failed and unscored attempts."""
    store = SqlAlchemyRunStore(session_factory)
    store.create(run())
    store.save_report(
        "run-1", {"outcomes": [{**generated_outcome(), **changes}]}
    )
    with session_factory() as session:
        assert (
            session.scalar(select(func.count()).select_from(PromptFindingRow))
            == 0
        )


def test_archive_preserves_invisible_characters_and_over_refusal_findings(
    session_factory: sessionmaker[Session],
) -> None:
    """Surface differences remain distinct even when they look alike."""
    store = SqlAlchemyRunStore(session_factory)
    store.create(run())
    first = generated_outcome("request")
    second = {
        **generated_outcome("re\u200bquest"),
        "variant_name": "recipe-2",
        "axis": "OR",
        "response_category": "REF",
        "attack_succeeded": None,
    }
    store.save_report("run-1", {"outcomes": [first, second]})
    with session_factory() as session:
        assert set(session.scalars(select(GeneratedPromptRow.text))) == {
            "request",
            "re\u200bquest",
        }
        assert (
            session.scalar(select(func.count()).select_from(PromptFindingRow))
            == 2
        )


def test_concurrent_report_delivery_archives_one_observation(
    tmp_path: Path,
) -> None:
    """Verify concurrent report delivery archives one observation."""
    engine = create_engine(f"sqlite:///{tmp_path / 'archive.sqlite'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    store = SqlAlchemyRunStore(factory)
    store.create(run())
    document = {
        "outcomes": [generated_outcome()],
        "target_model": "executed-model",
    }
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(
            pool.map(lambda _: store.save_report("run-1", document), range(8))
        )
    with factory() as session:
        assert (
            session.scalar(select(func.count()).select_from(PromptFindingRow))
            == 1
        )
        finding = session.scalars(select(PromptFindingRow)).one()
        assert finding.target_model == "executed-model"
    engine.dispose()


def test_archive_failure_rolls_back_report_and_prior_findings(
    session_factory: sessionmaker[Session],
) -> None:
    """A malformed finding cannot leave a partially saved report or archive."""
    store = SqlAlchemyRunStore(session_factory)
    store.create(run())
    document = {
        "outcomes": [
            generated_outcome(),
            {
                **generated_outcome(),
                "transcript": {"response": "missing sent prompt"},
            },
        ]
    }
    with pytest.raises(KeyError):
        store.save_report("run-1", document)
    with pytest.raises(UnknownRunError):
        store.get_report("run-1", "user-1")
    with session_factory() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(GeneratedPromptRow)
            )
            == 0
        )
        assert (
            session.scalar(select(func.count()).select_from(PromptFindingRow))
            == 0
        )


def test_snapshot_rejects_stale_verification_and_keeps_matching_key(
    session_factory: sessionmaker[Session],
) -> None:
    """Verification cannot overwrite a newer endpoint/key snapshot."""
    from harass.application.errors import ConflictError

    store = SqlAlchemyConnectionStore(session_factory)
    store.save(connection(), "first-key")
    original, original_key = store.snapshot("conn-1", "user-1")
    store.save(replace(original, model_name="new-model"), "second-key")
    with pytest.raises(ConflictError):
        store.save(replace(original, status=ConnectionStatus.CONNECTED), None)
    latest, latest_key = store.snapshot("conn-1", "user-1")
    assert original_key == "first-key" and latest_key == "second-key"
    assert (
        latest.model_name == "new-model"
        and latest.revision == original.revision + 1
    )
    assert latest.created_at is not None and latest.created_at.tzinfo is UTC


def test_sqlite_run_timestamps_retain_utc(
    session_factory: sessionmaker[Session],
) -> None:
    """Verify sqlite run timestamps retain utc."""
    store = SqlAlchemyRunStore(session_factory)
    store.create(run())
    restored = store.get("run-1", "user-1")
    assert restored.created_at == NOW and restored.created_at.tzinfo is UTC
