"""Tests for the run-management use case with in-memory fakes."""

from datetime import UTC, datetime
from typing import Any

import pytest

from harass.application.errors import ConnectionNotReadyError
from harass.application.evaluation_report import EvaluationReport, EvaluationRequest
from harass.application.ports.run_store import RunStore
from harass.application.use_cases.manage_runs import ManageRuns, RunParameters
from harass.domain.evaluation_run import EvaluationRun, RunStatus
from harass.domain.metrics import compute_metrics
from harass.domain.target_connection import TargetConnection

OWNER = "user-1"
TARGET = TargetConnection(base_url="https://api.invalid/v1", model_name="model", api_key="k")


class InMemoryRunStore(RunStore):
    """Keeps runs and report documents in dictionaries."""

    def __init__(self) -> None:
        """Start empty."""
        self.runs: dict[str, EvaluationRun] = {}
        self.reports: dict[str, dict[str, Any]] = {}

    def create(self, run: EvaluationRun) -> None:
        """Insert a run."""
        self.runs[run.run_id] = run

    def update(self, run: EvaluationRun) -> None:
        """Replace a run."""
        self.runs[run.run_id] = run

    def save_report(self, run_id: str, document: dict[str, Any]) -> None:
        """Store a report document."""
        self.reports[run_id] = document

    def get(self, run_id: str, owner_id: str) -> EvaluationRun:
        """Return a run."""
        return self.runs[run_id]

    def get_report(self, run_id: str, owner_id: str) -> dict[str, Any]:
        """Return a report document."""
        return self.reports[run_id]

    def list_for_owner(self, owner_id: str) -> list[EvaluationRun]:
        """Return all runs."""
        return list(self.runs.values())


class StubConnections:
    """Yields a fixed target, or refuses when the connection is not ready."""

    def __init__(self, ready: bool = True) -> None:
        """Remember whether the connection is ready."""
        self._ready = ready

    def target_for_evaluation(
        self, owner_id: str, connection_id: str, max_requests_per_minute: int | None = None
    ) -> TargetConnection:
        """Return the target or raise when not ready."""
        if not self._ready:
            raise ConnectionNotReadyError(connection_id)
        return TARGET


class StubEvaluation:
    """Returns a fixed empty report, or raises a scripted error."""

    def __init__(self, error: Exception | None = None) -> None:
        """Remember the error to raise, if any."""
        self._error = error

    async def execute(self, request: EvaluationRequest) -> EvaluationReport:
        """Return a report or fail."""
        if self._error:
            raise self._error
        return EvaluationReport(
            run_identifier="ignored",
            target_model=request.target.model_name,
            variant_names=(),
            include_baseline=True,
            outcomes=(),
            metrics=compute_metrics([]),
        )


def make(
    ready: bool = True, error: Exception | None = None
) -> tuple[ManageRuns, InMemoryRunStore]:
    """Return a run use case and its store, with the clock fixed."""
    store = InMemoryRunStore()
    use_case = ManageRuns(
        store,
        StubConnections(ready),  # type: ignore[arg-type]
        StubEvaluation(error),  # type: ignore[arg-type]
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )
    return use_case, store


def test_start_requires_a_ready_connection() -> None:
    """A run cannot start on a connection that has not passed its test."""
    use_case, _ = make(ready=False)

    with pytest.raises(ConnectionNotReadyError):
        use_case.start(OWNER, "conn-1", RunParameters())


async def test_successful_run_is_completed_with_a_report() -> None:
    """A finished run is marked completed and its report document is stored."""
    use_case, store = make()
    run = use_case.start(OWNER, "conn-1", RunParameters())

    finished = await use_case.execute(run, RunParameters())

    assert finished.status is RunStatus.COMPLETED
    assert store.runs[run.run_id].status is RunStatus.COMPLETED
    assert run.run_id in store.reports


async def test_failed_run_records_the_error() -> None:
    """An error marks the run failed without exposing provider exception content."""
    use_case, store = make(error=RuntimeError("engine down"))
    run = use_case.start(OWNER, "conn-1", RunParameters())

    finished = await use_case.execute(run, RunParameters())

    assert finished.status is RunStatus.FAILED
    assert finished.error == "Evaluation failed: RuntimeError."
    assert run.run_id not in store.reports
