"""Durable worker recovery, ownership and scale checks on isolated relational schemas."""

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from harass.application.errors import EvaluationEngineError, UnknownRunError
from harass.application.ports.attempt_executor import AttemptExecutor
from harass.application.ports.connection_verifier import ConnectionVerifier
from harass.application.ports.evaluation_journal import EvaluationJournal
from harass.application.ports.run_queue import EvaluationYieldedError, LeaseLostError
from harass.application.ports.seed_source import SeedSource
from harass.application.use_cases.manage_connections import ManageConnections
from harass.application.use_cases.manage_runs import ManageRuns, RunParameters
from harass.application.use_cases.process_runs import ProcessRuns
from harass.application.use_cases.run_evaluation import RunEvaluation
from harass.application.variant_evaluation_engine import VariantEvaluationEngine
from harass.domain.case_identifier import CaseIdentifier
from harass.domain.case_outcome import AttemptTranscript, CaseOutcome
from harass.domain.case_selection import CaseSelection
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.evaluation_plan import EvaluationPlan
from harass.domain.evaluation_run import EvaluationRun, RunStatus
from harass.domain.prompt_variant import (
    AdaptiveSettings,
    EvaluationMode,
    PromptVariant,
    VariantSelection,
)
from harass.domain.target_connection import TargetConnection
from harass.domain.taxonomy import ResponseCategory
from harass.infrastructure.dataset.yaml_variant_catalog import YamlVariantCatalog
from harass.infrastructure.persistence.sqlalchemy_jobs import SqlAlchemyRunQueue
from harass.infrastructure.persistence.sqlalchemy_stores import (
    SqlAlchemyConnectionStore,
    SqlAlchemyRunStore,
)
from harass.infrastructure.persistence.tables import Base, ConnectionRow, RunOutcomeRow, UserRow
from harass.infrastructure.security.fernet_secret_cipher import FernetSecretCipher
from harass.interfaces.api.app import create_app, owner_id

ROOT = Path(__file__).resolve().parents[3]
TARGET = TargetConnection("http://target.invalid/v1", "target", "test-only")
DIALECTS = ["sqlite"] + (["postgresql"] if os.environ.get("HARASS_TEST_DATABASE_URL") else [])


@dataclass
class Clock:
    """A controlled lease clock independent of wall-clock test duration."""

    now: datetime


@dataclass
class Storage:
    """Isolated worker storage and a shared controlled clock."""

    engine: Engine
    factory: sessionmaker[Session]
    queue: SqlAlchemyRunQueue
    runs: SqlAlchemyRunStore
    clock: Clock


@pytest.fixture(params=DIALECTS)
def storage(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Storage]:
    """Create a file database or a disposable PostgreSQL schema without touching public tables."""
    admin = None
    schema = "harass_test_" + uuid.uuid4().hex
    if request.param == "postgresql":
        url = os.environ["HARASS_TEST_DATABASE_URL"]
        admin = create_engine(url)
        with admin.begin() as connection:
            connection.execute(CreateSchema(schema))
        engine = create_engine(url, connect_args={"options": "-c search_path=" + schema})
    else:
        engine = create_engine(f"sqlite:///{tmp_path / 'durable.sqlite'}")
    try:
        Base.metadata.create_all(engine)
        factory = sessionmaker(engine)
        with factory.begin() as session:
            for number in (1, 2):
                owner = f"20000000-0000-4000-8000-{number:012d}"
                session.add(
                    UserRow(
                        user_id=owner,
                        full_name="Test",
                        email=f"user{number}@example.test",
                        password_hash="test-only",
                    )
                )
            session.flush()
            for number in (1, 2):
                session.add(
                    ConnectionRow(
                        connection_id=f"30000000-0000-4000-8000-{number:012d}",
                        owner_id=f"20000000-0000-4000-8000-{number:012d}",
                        base_url=TARGET.base_url,
                        model_name=TARGET.model_name,
                        status="connected",
                        encrypted_api_key="test-only",
                    )
                )
        clock = Clock(datetime.now(UTC))
        yield Storage(
            engine,
            factory,
            SqlAlchemyRunQueue(factory, "test-profile", "test-judge", clock=lambda: clock.now),
            SqlAlchemyRunStore(factory),
            clock,
        )
    finally:
        engine.dispose()

        if admin:
            with admin.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
            admin.dispose()


def enqueue(
    storage: Storage,
    run_id: str = "10000000-0000-4000-8000-000000000001",
    owner: str = "20000000-0000-4000-8000-000000000001",
) -> None:
    """Admit a neutral run without storing target credentials in its job document."""
    storage.queue.enqueue(
        EvaluationRun(
            run_id,
            owner,
            "30000000-0000-4000-8000-000000000001"
            if owner.endswith("001")
            else "30000000-0000-4000-8000-000000000002",
            "target",
            RunStatus.PENDING,
            storage.clock.now,
        ),
        RunParameters().document(),
        TARGET.base_url,
    )


def cases(count: int = 2) -> tuple[EvaluationCase, ...]:
    """Generate distinct neutral paired-case identifiers without an external model."""
    return tuple(
        EvaluationCase(
            CaseIdentifier.parse(f"OR-HSB-VIO-MSA-0{index:04d}"),
            f"Neutral request {index}",
            f"Neutral request {index}",
        )
        for index in range(count)
    )


class Executor(AttemptExecutor):
    """A neutral deterministic target used to measure storage and controller behavior."""

    def __init__(self) -> None:
        """Start with no submitted requests."""
        self.seen: list[str] = []

    async def execute(
        self,
        case: EvaluationCase,
        variant: PromptVariant,
        target: TargetConnection,
        run_identifier: str,
    ) -> CaseOutcome:
        """Return compliance and auditable text without any network requests."""
        self.seen.append(variant.variant_id)
        return CaseOutcome(
            case,
            variant.variant_id,
            ResponseCategory.FULL_COMPLIANCE,
            transcript=AttemptTranscript(variant.sent_prompt, "Synthetic response"),
            variant=variant,
        )


class Source(SeedSource):
    """Small immutable neutral data for worker and API integration checks."""

    def load_cases(self, selection: CaseSelection) -> list[EvaluationCase]:
        """Return four cases matching the supplied scope."""
        return [case for case in cases(4) if selection.matches(case)]


class Verifier(ConnectionVerifier):
    """Technical readiness without network access."""

    async def verify(self, target: TargetConnection) -> str | None:
        """Declare this isolated synthetic target ready."""
        return None


def connections(storage: Storage) -> ManageConnections:
    """Wire real connection ownership and encryption around the synthetic verifier."""
    return ManageConnections(
        SqlAlchemyConnectionStore(storage.factory),
        FernetSecretCipher(Fernet.generate_key().decode()),
        Verifier(),
    )


async def test_api_admission_worker_quanta_and_full_streamed_export(storage: Storage) -> None:
    """The HTTP request only queues work; a worker persists and exports every attempt."""
    import json

    resolver = connections(storage)
    executor = Executor()
    manager = ManageRuns(storage.runs, resolver, None, queue=storage.queue)
    app = create_app(resolver, manager)
    app.dependency_overrides[owner_id] = lambda: "20000000-0000-4000-8000-000000000001"
    worker = ProcessRuns(
        storage.queue,
        resolver,
        RunEvaluation(
            Source(),
            VariantEvaluationEngine(
                YamlVariantCatalog(ROOT / "config/templates"), executor, quantum_attempts=2
            ),
        ),
    )
    with TestClient(app) as client:
        connection = client.post(
            "/connections",
            json={
                "base_url": TARGET.base_url,
                "model_name": TARGET.model_name,
                "api_key": TARGET.api_key,
            },
        ).json()["connection_id"]
        assert client.post(f"/connections/{connection}/verify").status_code == 200
        created = client.post("/runs", json={"connection_id": connection, "run_type": "baseline"})
        assert created.status_code == 201 and created.json()["status"] == "pending"
        identifier = created.json()["run_id"]
        assert executor.seen == []
        assert await worker.once()
        progress = client.get(f"/runs/{identifier}").json()
        assert progress["status"] == "pending" and progress["completed_cases"] == 2
        assert await worker.once()
        summary = client.get(f"/runs/{identifier}/report").json()
        assert summary["evidence_paged"] and summary["outcomes"] == []
        assert summary["outcomes_count"] == 4
        page = client.get(f"/runs/{identifier}/outcomes?limit=1&offset=1").json()
        assert page["total"] == 4 and len(page["items"]) == 1
        export = client.get(f"/runs/{identifier}/report/export")
        assert len(json.loads(export.text)["outcomes"]) == 4
        assert export.headers["content-disposition"].startswith("attachment;")
        app.dependency_overrides[owner_id] = lambda: "20000000-0000-4000-8000-000000000003"
        assert client.get(f"/runs/{identifier}/outcomes").status_code == 404
        assert client.get(f"/runs/{identifier}/report/export").status_code == 404


class UnavailableExecutor(Executor):
    """Simulate service failure followed by operator recovery."""

    def __init__(self) -> None:
        """Start unavailable without making network calls."""
        super().__init__()
        self.available = False

    async def execute(
        self,
        case: EvaluationCase,
        variant: PromptVariant,
        target: TargetConnection,
        run_identifier: str,
    ) -> CaseOutcome:
        """Return a technical failure or delegate after service recovery."""
        if self.available:
            return await super().execute(case, variant, target, run_identifier)
        self.seen.append(variant.variant_id)
        return CaseOutcome(
            case, variant.variant_id, error="Attempt failed: ConnectionError.", variant=variant
        )


async def test_repeated_failures_suspend_and_resume_without_resetting_budget(
    storage: Storage,
) -> None:
    """Stop after three technical failures and preserve those unknown outcomes on recovery."""
    resolver = connections(storage)
    connection = resolver.add(
        "20000000-0000-4000-8000-000000000001", TARGET.base_url, TARGET.model_name, TARGET.api_key
    )
    await resolver.verify("20000000-0000-4000-8000-000000000001", connection.connection_id)
    manager = ManageRuns(storage.runs, resolver, None, queue=storage.queue)
    run = manager.start(
        "20000000-0000-4000-8000-000000000001",
        connection.connection_id,
        RunParameters(
            variant_selection=VariantSelection((), ()),
        ),
    )
    executor = UnavailableExecutor()
    worker = ProcessRuns(
        storage.queue,
        resolver,
        RunEvaluation(
            Source(),
            VariantEvaluationEngine(YamlVariantCatalog(ROOT / "config/templates"), executor),
        ),
    )
    assert await worker.once()
    failed = manager.get("20000000-0000-4000-8000-000000000001", run.run_id)
    assert failed.status is RunStatus.FAILED and failed.resumable
    assert failed.completed_attempts == 3
    with pytest.raises(UnknownRunError):
        manager.resume("20000000-0000-4000-8000-000000000003", run.run_id)
    executor.available = True
    manager.resume("20000000-0000-4000-8000-000000000001", run.run_id)
    assert await worker.once()
    assert (
        manager.get("20000000-0000-4000-8000-000000000001", run.run_id).status
        is RunStatus.COMPLETED
    )
    assert len(executor.seen) == 4
    summary = manager.get_report("20000000-0000-4000-8000-000000000001", run.run_id)
    assert summary["metrics"]["unscored_outcomes"] == 3


class InterruptedJournal(EvaluationJournal):
    """Interrupt after a durable reservation or commit to simulate worker loss."""

    def __init__(self, inner: EvaluationJournal, *, reserve: int = 0, commit: int = 0) -> None:
        """Choose the atomic operation after which execution is interrupted."""
        self.inner, self.reserve_at, self.commit_at = inner, reserve, commit
        self.reservations = self.commits = 0

    def initialize(self, fingerprint: str, total_cases: int) -> dict[str, Any]:
        """Delegate initialization."""
        return self.inner.initialize(fingerprint, total_cases)

    def reserve(self, checkpoint: dict[str, Any]) -> None:
        """Persist first, then interrupt at the configured submission boundary."""
        self.inner.reserve(checkpoint)
        self.reservations += 1
        if self.reservations == self.reserve_at:
            raise RuntimeError("Simulated worker loss")

    def commit(self, outcome: CaseOutcome, checkpoint: dict[str, Any]) -> None:
        """Persist first, then interrupt at the configured feedback boundary."""
        self.inner.commit(outcome, checkpoint)
        self.commits += 1
        if self.commits == self.commit_at:
            raise RuntimeError("Simulated worker loss")

    def outcomes(self, *, lightweight: bool = False) -> Iterator[CaseOutcome]:
        """Delegate bounded outcome reads."""
        return self.inner.outcomes(lightweight=lightweight)


def test_worker_leases_fence_expired_owners_and_preserve_queue_fairness(storage: Storage) -> None:
    """Only one worker owns the judge; renewed or reclaimed leases exclude stale commits."""
    enqueue(storage)
    enqueue(
        storage,
        "10000000-0000-4000-8000-000000000002",
        owner="20000000-0000-4000-8000-000000000002",
    )
    first = storage.queue.claim("first")
    assert first is not None
    assert storage.queue.claim("other") is None
    journal = storage.queue.journal(first)
    journal.initialize("plan", 1)
    storage.clock.now += timedelta(seconds=121)
    second = storage.queue.claim("second")
    assert second is not None and second.run.run_id == "10000000-0000-4000-8000-000000000001"
    with pytest.raises(LeaseLostError):
        journal.reserve({"case_index": 0})
    storage.queue.release(first)
    assert storage.queue.claim("third") is None
    storage.queue.release(second)
    recovered = storage.queue.claim("third")
    assert recovered is not None and recovered.run.run_id == "10000000-0000-4000-8000-000000000002"


async def test_restart_preserves_random_choices_and_committed_feedback(storage: Storage) -> None:
    """A fresh engine follows the same adaptive sequence after a committed checkpoint."""
    catalogue = YamlVariantCatalog(ROOT / "config/templates")
    plan = EvaluationPlan(
        cases(),
        True,
        VariantSelection(transform_names=()),
        AdaptiveSettings(EvaluationMode.ADAPTIVE, 3, 19),
    )
    expected = await VariantEvaluationEngine(catalogue, Executor()).evaluate(
        plan, TARGET, "reference"
    )
    enqueue(storage)
    first = storage.queue.claim("first")
    assert first is not None
    executor = Executor()
    with pytest.raises(RuntimeError, match="Simulated worker"):
        await VariantEvaluationEngine(catalogue, executor).evaluate(
            plan,
            TARGET,
            "10000000-0000-4000-8000-000000000001",
            journal=InterruptedJournal(storage.queue.journal(first), commit=3),
        )
    storage.queue.release(first)
    second = storage.queue.claim("second")
    assert second is not None
    actual = await VariantEvaluationEngine(catalogue, executor).evaluate(
        plan, TARGET, "10000000-0000-4000-8000-000000000001", journal=storage.queue.journal(second)
    )
    assert [(o.variant_name, o.posterior_before, o.stop_reason) for o in actual] == [
        (o.variant_name, o.posterior_before, o.stop_reason) for o in expected
    ]
    assert len(executor.seen) == len(expected)
    assert (
        storage.runs.get(
            "10000000-0000-4000-8000-000000000001", "20000000-0000-4000-8000-000000000001"
        ).completed_cases
        == 2
    )


async def test_ambiguous_submission_is_not_resent_or_learned(storage: Storage) -> None:
    """An interrupted reserved slot consumes budget as unknown without a duplicate request."""
    plan = EvaluationPlan(
        cases(1),
        True,
        VariantSelection(transform_names=()),
        AdaptiveSettings(EvaluationMode.ADAPTIVE, 3, 19),
    )
    catalogue, executor = YamlVariantCatalog(ROOT / "config/templates"), Executor()
    enqueue(storage)
    first = storage.queue.claim("first")
    assert first is not None
    with pytest.raises(RuntimeError):
        await VariantEvaluationEngine(catalogue, executor).evaluate(
            plan,
            TARGET,
            "10000000-0000-4000-8000-000000000001",
            journal=InterruptedJournal(storage.queue.journal(first), reserve=3),
        )
    storage.queue.release(first)
    second = storage.queue.claim("second")
    assert second is not None
    outcomes = await VariantEvaluationEngine(catalogue, executor).evaluate(
        plan, TARGET, "10000000-0000-4000-8000-000000000001", journal=storage.queue.journal(second)
    )
    uncertain = [o for o in outcomes if o.submission_uncertain]
    assert len(uncertain) == 1 and not uncertain[0].is_scored
    assert uncertain[0].variant_name not in executor.seen
    assert len(outcomes) == 4 and len(executor.seen) == 3


def test_changed_plan_and_evidence_ownership_are_rejected(storage: Storage) -> None:
    """No worker may mix changed inputs or expose another owner's stored attempts."""
    enqueue(storage)
    job = storage.queue.claim("first")
    assert job is not None
    journal = storage.queue.journal(job)
    journal.initialize("original", 2)
    with pytest.raises(EvaluationEngineError):
        journal.initialize("changed", 2)
    with pytest.raises(UnknownRunError):
        storage.queue.outcome_page(
            "10000000-0000-4000-8000-000000000001", "20000000-0000-4000-8000-000000000003", 0, 50
        )


@pytest.mark.scale
@pytest.mark.parametrize("mode", ["baseline", "agentic"])
async def test_ten_thousand_cases_checkpoint_and_complete_in_bounded_quanta(
    storage: Storage,
    mode: str,
) -> None:
    """Exercise 10,000 durable synthetic cases without sending any model requests."""
    enqueue(storage)
    selection = VariantSelection((), ()) if mode == "baseline" else VariantSelection()
    plan = EvaluationPlan(
        cases(10000),
        True,
        selection,
        AdaptiveSettings(
            EvaluationMode.STATIC if mode == "baseline" else EvaluationMode.ADAPTIVE, 8, 19
        ),
    )
    executor = Executor()
    engine = VariantEvaluationEngine(
        YamlVariantCatalog(ROOT / "config/templates"), executor, quantum_attempts=1000
    )
    outcomes: list[CaseOutcome] = []
    total = 10000 if mode == "baseline" else 90000
    for index in range(total // 1000):
        job = storage.queue.claim(f"worker-{index}")
        assert job is not None
        try:
            outcomes = await engine.evaluate(
                plan,
                TARGET,
                "10000000-0000-4000-8000-000000000001",
                journal=storage.queue.journal(job),
            )
        except EvaluationYieldedError:
            assert index < total // 1000 - 1
        finally:
            storage.queue.release(job)
            storage.clock.now += timedelta(seconds=1)
        if (index + 1) % 10 == 0:
            print(f"Committed synthetic attempts: {len(executor.seen)}/{total}", flush=True)
    assert len(outcomes) == len(executor.seen) == total
    assert all(outcome.transcript is None for outcome in outcomes)
    run = storage.runs.get(
        "10000000-0000-4000-8000-000000000001", "20000000-0000-4000-8000-000000000001"
    )
    assert run.completed_cases == run.total_cases == 10000
    assert run.completed_attempts == total
    assert (
        len(
            storage.queue.outcome_page(
                "10000000-0000-4000-8000-000000000001",
                "20000000-0000-4000-8000-000000000001",
                total - 50,
                50,
            )["items"]
        )
        == 50
    )
    with storage.factory() as session:
        assert session.scalar(select(func.count()).select_from(RunOutcomeRow)) == total


def test_cancellation_fences_worker_and_releases_account_budget(storage: Storage) -> None:
    """Cancellation preserves the run and prevents its old worker from renewing ownership."""
    from harass.application.errors import ActiveRunError

    enqueue(storage)
    job = storage.queue.claim("old-worker")
    assert job is not None
    with pytest.raises(ActiveRunError):
        enqueue(storage, "10000000-0000-4000-8000-000000000002")
    cancelled = storage.queue.cancel(job.run.run_id, job.run.owner_id)
    assert cancelled.status is RunStatus.CANCELLED
    assert cancelled.started_at is not None and cancelled.finished_at is not None
    assert cancelled.lifecycle_events[-1]["event"] == "cancelled"
    with pytest.raises(LeaseLostError):
        storage.queue.renew(job)
    enqueue(storage, "10000000-0000-4000-8000-000000000002")
    assert storage.queue.claim("new-worker") is None
    storage.queue.release(job)
    assert storage.queue.claim("new-worker") is not None


def test_postgresql_rejects_cross_account_connection_and_invalid_progress(
    storage: Storage,
) -> None:
    """Database constraints independently reject invalid ownership and lifecycle values."""
    from sqlalchemy import insert
    from sqlalchemy.exc import IntegrityError

    from harass.infrastructure.persistence.tables import RunRow

    if storage.engine.dialect.name != "postgresql":
        pytest.skip("Native PostgreSQL ownership constraints")
    invalid_values: list[dict[str, object]] = [
        {"connection_id": "30000000-0000-4000-8000-000000000002"},
        {"status": "unknown"},
        {"total_cases": 1, "completed_cases": 2},
        {"completed_attempts": -1},
    ]
    for invalid in invalid_values:
        values = dict(
            run_id=str(uuid.uuid4()),
            owner_id="20000000-0000-4000-8000-000000000001",
            connection_id="30000000-0000-4000-8000-000000000001",
            target_model="test",
            status="completed",
            created_at=storage.clock.now,
        )
        with pytest.raises(IntegrityError), storage.engine.begin() as database:
            database.execute(insert(RunRow).values(**(values | invalid)))
    assert storage.runs.list_for_owner("20000000-0000-4000-8000-000000000001") == []
