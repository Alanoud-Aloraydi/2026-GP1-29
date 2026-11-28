"""Tests for the HTTP API with in-memory use cases and no real model calls."""

import asyncio
import re
from collections.abc import Iterator
from typing import cast

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from harass.application.connections import ManageConnections
from harass.application.evaluation.contracts import EvaluationReport, EvaluationRequest
from harass.application.evaluation.run_service import ManageRuns
from harass.application.evaluation.runner import RunEvaluation
from harass.application.evaluation.worker import ProcessRuns
from harass.application.ports.connections import ConnectionVerifier
from harass.application.ports.evaluation import EvaluationJournal
from harass.domain.generation.attack_briefs import ATTACK_DEVICES
from harass.domain.generation.over_refusal_briefs import MECHANISMS
from harass.domain.metrics import compute_metrics
from harass.domain.target_connection import TargetConnection
from harass.infrastructure.persistence.sqlalchemy_connections import SqlAlchemyConnectionStore
from harass.infrastructure.persistence.sqlalchemy_generation import SqlAlchemyGeneratedEvidence
from harass.infrastructure.persistence.sqlalchemy_jobs import SqlAlchemyRunQueue
from harass.infrastructure.persistence.sqlalchemy_runs import SqlAlchemyRunStore
from harass.infrastructure.persistence.tables import Base
from harass.infrastructure.security.fernet_secret_cipher import FernetSecretCipher
from harass.interfaces.api.accounts.dependencies import authenticated_owner
from harass.interfaces.api.app import create_app

OWNER_HEADER = {"X-Owner-Id": "user-1"}
ARABIC = re.compile(r"[؀-ۿ]")


class StubEvaluation:
    """Returns a fixed empty report."""

    async def execute(
        self, request: EvaluationRequest, *, journal: EvaluationJournal | None = None
    ) -> EvaluationReport:
        """Return an empty report for the request's target."""
        assert request.run_identifier is not None
        return EvaluationReport(
            run_identifier=request.run_identifier,
            target_model=request.target.model_name,
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
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    connections = ManageConnections(
        SqlAlchemyConnectionStore(factory),
        FernetSecretCipher(Fernet.generate_key().decode("ascii")),
        PassingVerifier(),
    )
    queue = SqlAlchemyRunQueue(factory, "api-fixture", "api-judge")
    runs = ManageRuns(
        SqlAlchemyRunStore(factory),
        connections,
        queue=queue,
        generated=SqlAlchemyGeneratedEvidence(factory),
    )
    app = create_app(connections, runs)
    app.state.test_worker = ProcessRuns(
        queue, connections, cast(RunEvaluation, StubEvaluation()), None
    )
    # This isolated fixture bypasses authentication explicitly, never through a
    # production header.
    app.dependency_overrides[authenticated_owner] = lambda: "user-1"
    with TestClient(app) as client:
        yield client
    engine.dispose()


def add_connection(client: TestClient) -> str:
    """Add a connection and return its id."""
    response = client.post(
        "/connections",
        json={"base_url": "https://api.invalid/v1", "model_name": "model", "api_key": "secret"},
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


def test_claimed_owner_header_is_not_authentication(client: TestClient) -> None:
    """Verify claimed owner header is not authentication."""
    cast(FastAPI, client.app).dependency_overrides.clear()
    assert client.get("/connections", headers=OWNER_HEADER).status_code == 401


def test_run_requires_a_verified_connection(client: TestClient) -> None:
    """Starting a run on an untested connection is a conflict."""
    connection_id = add_connection(client)

    response = client.post("/runs", json={"connection_id": connection_id}, headers=OWNER_HEADER)
    assert response.status_code == 409


def test_run_completes_and_exposes_its_report(client: TestClient) -> None:
    """Verify run completes and exposes its report."""
    connection_id = add_connection(client)
    assert (
        client.post(f"/connections/{connection_id}/verify", headers=OWNER_HEADER).json()["status"]
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


def test_evaluation_options_list_the_dataset_classifications(client: TestClient) -> None:
    """Verify the options list the dataset's classifications and nothing else."""
    response = client.get("/evaluation-options", headers=OWNER_HEADER)
    assert response.status_code == 200
    assert "MSA" in response.json()["varieties"]
    assert set(response.json()["owasp_categories"]) == {"LLM01", "LLM02", "LLM07", "LLM08", "NAP"}
    assert not {"templates", "transforms"} & response.json().keys()
    agentic = response.json()["agentic"]
    assert (agentic["max_rounds"], agentic["max_prompts_per_round"]) == (5, 50)
    transforms = {item["name"]: item for item in agentic["transforms"]}
    assert transforms["arabizi"]["attack_only"] and not transforms["tatweel"]["attack_only"]
    assert all(item["label"] for item in agentic["transforms"])


def test_every_code_and_pattern_the_pages_show_has_an_arabic_label(client: TestClient) -> None:
    """Verify the page never falls back to a raw code for a classification or a pattern."""
    options = client.get("/evaluation-options", headers=OWNER_HEADER).json()
    codes = {
        *options["subject_domains"],
        *options["risk_categories"],
        *options["strategies"],
        *options["owasp_categories"],
    }
    assert codes <= options["labels"].keys()
    assert set(options["varieties"]) <= options["dialects"].keys()
    patterns = {code for devices in ATTACK_DEVICES.values() for code in devices} | set(MECHANISMS)
    assert patterns == options["devices"].keys()
    assert all(ARABIC.search(label) for label in options["devices"].values())


def test_an_agentic_run_without_a_baseline_runs_one_first(client: TestClient) -> None:
    """A missing baseline is admitted first; the agentic run waits until it completes."""
    connection_id = add_connection(client)
    client.post(f"/connections/{connection_id}/verify", headers=OWNER_HEADER)
    response = client.post(
        "/runs",
        json={"connection_id": connection_id, "kind": "agentic", "selection": {"axis": "OR"}},
        headers=OWNER_HEADER,
    )
    assert response.status_code == 201
    agentic = response.json()
    baseline_id = agentic["awaits_run_id"]
    baseline = client.get(f"/runs/{baseline_id}", headers=OWNER_HEADER).json()
    assert (baseline["kind"], baseline["status"]) == ("baseline", "pending")
    assert asyncio.run(cast(FastAPI, client.app).state.test_worker.once())
    assert client.get(f"/runs/{baseline_id}", headers=OWNER_HEADER).json()["status"] == "completed"
    waited = client.get(f"/runs/{agentic['run_id']}", headers=OWNER_HEADER).json()
    assert (waited["status"], waited["awaits_run_id"]) == ("pending", None)
    prompts = client.get(f"/runs/{agentic['run_id']}/prompts", headers=OWNER_HEADER)
    assert (prompts.status_code, prompts.json()["total"]) == (200, 0)


def test_an_agentic_run_follows_a_finished_baseline(client: TestClient) -> None:
    """After a baseline run completes, an agentic run is admitted with its rounds."""
    connection_id = add_connection(client)
    client.post(f"/connections/{connection_id}/verify", headers=OWNER_HEADER)
    client.post("/runs", json={"connection_id": connection_id}, headers=OWNER_HEADER)
    assert asyncio.run(cast(FastAPI, client.app).state.test_worker.once())
    response = client.post(
        "/runs",
        json={
            "connection_id": connection_id,
            "kind": "agentic",
            "agentic": {"rounds": 2, "prompts_per_round": 5, "transform_names": ["tatweel"]},
        },
        headers=OWNER_HEADER,
    )
    assert response.status_code == 201
    assert response.json()["kind"] == "agentic"


@pytest.mark.parametrize(
    "body",
    [
        {"selection": {"axis": "INVALID"}},
        {"run_type": "agentic"},
        {"max_base_cases_per_axis": 0},
        {"selection": {"varieties": ["UNKNOWN"]}},
        {"kind": "agentic", "agentic": {"rounds": 6}},
        {"kind": "agentic", "agentic": {"prompts_per_round": 51}},
        {"kind": "unknown"},
    ],
)
def test_invalid_evaluation_parameters_are_rejected(
    client: TestClient, body: dict[str, object]
) -> None:
    """Malformed or unknown parameters fail before a run is created."""
    response = client.post("/runs", headers=OWNER_HEADER, json={"connection_id": "unused", **body})
    assert response.status_code == 422
