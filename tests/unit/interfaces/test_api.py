"""Tests for the HTTP API with in-memory use cases and no real model calls."""

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from harass.application.connections import ManageConnections
from harass.application.evaluation.contracts import (
    EvaluationReport,
    EvaluationRequest,
)
from harass.application.evaluation.run_service import ManageRuns
from harass.application.evaluation.runner import RunEvaluation
from harass.application.evaluation.worker import ProcessRuns
from harass.application.ports.connection_verifier import ConnectionVerifier
from harass.application.ports.evaluation_journal import EvaluationJournal
from harass.domain.metrics import compute_metrics
from harass.domain.target_connection import TargetConnection
from harass.infrastructure.dataset.yaml_variant_catalog import (
    YamlVariantCatalog,
)
from harass.infrastructure.persistence.sqlalchemy_connections import (
    SqlAlchemyConnectionStore,
)
from harass.infrastructure.persistence.sqlalchemy_jobs import (
    SqlAlchemyRunQueue,
)
from harass.infrastructure.persistence.sqlalchemy_runs import (
    SqlAlchemyRunStore,
)
from harass.infrastructure.persistence.tables import Base
from harass.infrastructure.security.fernet_secret_cipher import (
    FernetSecretCipher,
)
from harass.interfaces.api.app import create_app, owner_id

OWNER_HEADER = {"X-Owner-Id": "user-1"}


class StubEvaluation:
    """Returns a fixed empty report."""

    async def execute(
        self,
        request: EvaluationRequest,
        *,
        journal: EvaluationJournal | None = None,
    ) -> EvaluationReport:
        """Return an empty report for the request's target."""
        assert request.run_identifier is not None
        return EvaluationReport(
            run_identifier=request.run_identifier,
            target_model=request.target.model_name,
            variant_names=(),
            include_baseline=True,
            outcomes=(),
            metrics=compute_metrics([]),
        )


class PassingVerifier(ConnectionVerifier):
    """Reports every connection as reachable."""

    async def verify(self, target: TargetConnection) -> str | None:
        """Accept the connection."""
        return None


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Return a TestClient wired to SQLite stores and stub evaluation."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    connections = ManageConnections(
        SqlAlchemyConnectionStore(factory),
        FernetSecretCipher(Fernet.generate_key().decode("ascii")),
        PassingVerifier(),
    )
    queue = SqlAlchemyRunQueue(factory, "api-fixture", "api-judge")
    runs = ManageRuns(SqlAlchemyRunStore(factory), connections, queue=queue)
    catalog = YamlVariantCatalog(
        Path(__file__).resolve().parents[3] / "config" / "templates"
    )
    app = create_app(connections, runs, catalog)
    app.state.test_worker = ProcessRuns(
        queue, connections, cast(RunEvaluation, StubEvaluation())
    )
    # This isolated fixture bypasses authentication explicitly, never through a
    # production header.
    app.dependency_overrides[owner_id] = lambda: "user-1"
    with TestClient(app) as client:
        yield client
    engine.dispose()


def add_connection(client: TestClient) -> str:
    """Add a connection and return its id."""
    response = client.post(
        "/connections",
        json={
            "base_url": "https://api.invalid/v1",
            "model_name": "model",
            "api_key": "secret",
        },
        headers=OWNER_HEADER,
    )
    assert response.status_code == 201
    connection_id: str = response.json()["connection_id"]
    return connection_id


def test_added_connection_never_returns_the_key(client: TestClient) -> None:
    """The connection response carries no API key."""
    add_connection(client)

    listed = client.get("/connections", headers=OWNER_HEADER).json()
    assert listed[0]["status"] == "not_tested"
    assert "api_key" not in listed[0] and "secret" not in str(listed)


def test_claimed_owner_header_is_not_authentication(
    client: TestClient,
) -> None:
    """Verify claimed owner header is not authentication."""
    cast(FastAPI, client.app).dependency_overrides.clear()
    assert client.get("/connections", headers=OWNER_HEADER).status_code == 401


def test_run_requires_a_verified_connection(client: TestClient) -> None:
    """Starting a run on an untested connection is a conflict."""
    connection_id = add_connection(client)

    response = client.post(
        "/runs", json={"connection_id": connection_id}, headers=OWNER_HEADER
    )
    assert response.status_code == 409


def test_run_completes_and_exposes_its_report(client: TestClient) -> None:
    """Verify run completes and exposes its report."""
    connection_id = add_connection(client)
    assert (
        client.post(
            f"/connections/{connection_id}/verify", headers=OWNER_HEADER
        ).json()["status"]
        == "connected"
    )

    run_id = client.post(
        "/runs", json={"connection_id": connection_id}, headers=OWNER_HEADER
    ).json()["run_id"]

    pending = client.get(f"/runs/{run_id}", headers=OWNER_HEADER).json()
    assert pending["status"] == "pending"
    assert asyncio.run(cast(FastAPI, client.app).state.test_worker.once())
    status = client.get(f"/runs/{run_id}", headers=OWNER_HEADER).json()
    assert status["status"] == "completed"
    report = client.get(f"/runs/{run_id}/report", headers=OWNER_HEADER)
    assert report.status_code == 200
    assert report.json()["target_model"] == "model"


def test_unknown_run_is_not_found(client: TestClient) -> None:
    """An unknown run id yields 404."""
    assert client.get("/runs/missing", headers=OWNER_HEADER).status_code == 404


def test_evaluation_options_are_real_library_metadata(
    client: TestClient,
) -> None:
    """Verify evaluation options are real library metadata."""
    response = client.get("/evaluation-options", headers=OWNER_HEADER)
    assert response.status_code == 200
    assert len(response.json()["templates"]) == 16
    assert "MSA" in response.json()["varieties"]
    assert "tatweel" in {
        entry["name"] for entry in response.json()["transforms"]
    }


@pytest.mark.parametrize(
    "body",
    [
        {"selection": {"axis": "INVALID"}},
        {"evaluation_mode": "multi_turn"},
        {"attempt_budget": 0},
        {"selection": {"varieties": ["UNKNOWN"]}},
    ],
)
def test_invalid_evaluation_parameters_are_rejected(
    client: TestClient, body: dict[str, object]
) -> None:
    """Malformed classifications and budgets fail before a run is created."""
    response = client.post(
        "/runs", headers=OWNER_HEADER, json={"connection_id": "unused", **body}
    )
    assert response.status_code == 422
