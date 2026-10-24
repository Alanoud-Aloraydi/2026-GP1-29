"""Run admission coordinates ownership and durable ports without execution."""

import json
from datetime import UTC, datetime
from typing import cast
from unittest.mock import Mock

import pytest

from harass.application.connections import ManageConnections
from harass.application.errors import ApplicationError, ConnectionNotReadyError
from harass.application.evaluation.parameters import RunParameters
from harass.application.evaluation.run_service import ManageRuns
from harass.application.ports.run_admission import RunAdmission
from harass.application.ports.run_store import RunStore
from harass.domain.evaluation_run import RunStatus
from harass.domain.target_connection import TargetConnection

OWNER = "user-1"
TARGET = TargetConnection("https://api.invalid/v1", "model", "private-key")


def services() -> tuple[ManageRuns, Mock, Mock, Mock]:
    """Compose admission with recording ports and a fixed clock."""
    connections = Mock(spec=ManageConnections)
    connections.target_for_evaluation.return_value = TARGET
    queue = Mock(spec=RunAdmission)
    store = Mock(spec=RunStore)
    use_case = ManageRuns(
        store,
        connections,
        queue=queue,
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )
    return use_case, store, connections, queue


def test_start_requires_a_ready_connection() -> None:
    """Unverified connections cannot create queued work."""
    use_case, _, connections, queue = services()
    connections.target_for_evaluation.side_effect = ConnectionNotReadyError()
    with pytest.raises(ConnectionNotReadyError):
        use_case.start(OWNER, "conn-1", RunParameters())
    queue.enqueue.assert_not_called()


def test_start_persists_job_inputs_without_credentials() -> None:
    """Starting a run queues immutable inputs without executing a model."""
    use_case, store, connections, queue = services()
    run = use_case.start(OWNER, "conn-1", RunParameters())
    assert run.status is RunStatus.PENDING
    connections.target_for_evaluation.assert_called_once_with(OWNER, "conn-1")
    queued_run, parameters, endpoint = queue.enqueue.call_args.args
    assert queued_run == run
    assert endpoint == TARGET.base_url
    assert "private-key" not in json.dumps(parameters)
    assert parameters["connection_revision"] == TARGET.connection_revision
    store.create.assert_not_called()


def test_lifecycle_and_evidence_preserve_owner_scope() -> None:
    """Resume, cancellation and evidence use the authenticated owner."""
    use_case, _, _, queue = services()
    use_case.resume(OWNER, "run-1")
    use_case.cancel(OWNER, "run-1")
    use_case.outcome_page(OWNER, "run-1", 100, 50)
    queue.resume.assert_called_once_with("run-1", OWNER)
    queue.cancel.assert_called_once_with("run-1", OWNER)
    queue.outcome_page.assert_called_once_with("run-1", OWNER, 100, 50)


def test_inconsistent_evidence_page_cannot_loop_forever() -> None:
    """A stalled evidence source fails instead of yielding a partial export."""
    admission = cast(RunAdmission, Mock(spec=RunAdmission))
    cast(Mock, admission).outcome_page.return_value = {"items": [], "total": 1}
    with pytest.raises(ApplicationError, match="incomplete"):
        list(RunAdmission.outcome_documents(admission, "run-1", OWNER))
