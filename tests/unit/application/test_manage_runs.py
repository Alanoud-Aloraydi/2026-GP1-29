"""Run admission coordinates ownership and durable ports without execution."""

import json
from datetime import UTC, datetime
from typing import cast
from unittest.mock import Mock

import pytest

from harass.application.connections import ManageConnections
from harass.application.errors import ApplicationError, ConnectionNotReadyError
from harass.application.evaluation.contracts import AgenticParameters, RunParameters
from harass.application.evaluation.run_service import ManageRuns
from harass.application.ports.generation import GeneratedEvidence
from harass.application.ports.runs import RunAdmission, RunStore
from harass.domain.case_selection import CaseSelection
from harass.domain.evaluation_run import EvaluationRun, RunKind, RunStatus
from harass.domain.target_connection import TargetConnection
from harass.domain.taxonomy import ArabicVariety, Axis

OWNER = "user-1"
TARGET = TargetConnection("https://api.invalid/v1", "model", "private-key")


CREATED = datetime(2026, 1, 1, tzinfo=UTC)


def services() -> tuple[ManageRuns, Mock, Mock, Mock]:
    """Compose admission with recording ports and a fixed clock."""
    connections = Mock(spec=ManageConnections)
    connections.target_for_evaluation.return_value = TARGET
    queue = Mock(spec=RunAdmission)
    store = Mock(spec=RunStore)
    store.get.return_value = run_of(RunKind.BASELINE)
    use_case = ManageRuns(
        store,
        connections,
        queue=queue,
        generated=Mock(spec=GeneratedEvidence),
        clock=lambda: CREATED,
    )
    return use_case, store, connections, queue


def run_of(kind: RunKind) -> EvaluationRun:
    """Return a stored run of one kind."""
    return EvaluationRun("run-1", OWNER, "conn-1", "model", RunStatus.COMPLETED, CREATED, kind=kind)


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
    assert run.kind is RunKind.BASELINE
    assert not store.method_calls


def baseline(run_id: str, status: RunStatus) -> EvaluationRun:
    """Return a baseline run on the test connection in one status."""
    return EvaluationRun(run_id, OWNER, "conn-1", "model", status, CREATED)


def test_an_agentic_run_starts_from_the_latest_completed_baseline() -> None:
    """A completed baseline covering both axes is preferred to one still running."""
    use_case, store, _, queue = services()
    store.baselines.return_value = [
        (baseline("base-2", RunStatus.RUNNING), None),
        (baseline("base-1", RunStatus.COMPLETED), None),
    ]
    run = use_case.start_agentic(
        OWNER,
        "conn-1",
        rounds=2,
        prompts_per_round=10,
        transform_names=("tatweel",),
        varieties=frozenset({ArabicVariety.NAJDI}),
    )
    queued_run, parameters, _ = queue.enqueue.call_args.args
    assert queue.enqueue.call_count == 1
    assert queued_run == run
    assert run.kind is RunKind.AGENTIC
    assert run.awaits_run_id is None
    assert AgenticParameters.from_document(parameters) == AgenticParameters(
        "base-1",
        axes=(Axis.OVER_REFUSAL, Axis.ADVERSARIAL),
        rounds=2,
        prompts_per_round=10,
        transform_names=("tatweel",),
        varieties=frozenset({ArabicVariety.NAJDI}),
    )
    store.baselines.assert_called_once_with(OWNER, "conn-1")


def test_an_agentic_run_waits_for_an_active_baseline_on_its_axis() -> None:
    """A running baseline limited to the chosen axis is awaited, not run twice."""
    use_case, store, _, queue = services()
    store.baselines.return_value = [(baseline("base-1", RunStatus.PENDING), Axis.OVER_REFUSAL)]
    run = use_case.start_agentic(
        OWNER, "conn-1", axis=Axis.OVER_REFUSAL, rounds=1, prompts_per_round=5
    )
    assert queue.enqueue.call_count == 1
    assert run.awaits_run_id == "base-1"
    parameters = AgenticParameters.from_document(queue.enqueue.call_args.args[1])
    assert parameters.axes == (Axis.OVER_REFUSAL,)
    assert parameters.baseline_run_id == "base-1"


def test_a_missing_baseline_is_admitted_first_and_awaited() -> None:
    """A baseline on one axis does not cover both, so one on both axes runs first."""
    use_case, store, _, queue = services()
    store.baselines.return_value = [(baseline("base-1", RunStatus.COMPLETED), Axis.OVER_REFUSAL)]
    varieties = frozenset({ArabicVariety.EGYPTIAN})
    run = use_case.start_agentic(
        OWNER, "conn-1", rounds=1, prompts_per_round=5, varieties=varieties
    )
    (first, first_parameters, _), (second, second_parameters, _) = (
        call.args for call in queue.enqueue.call_args_list
    )
    assert first.kind is RunKind.BASELINE
    assert RunParameters.from_document(first_parameters) == RunParameters(
        CaseSelection(axis=None, varieties=varieties)
    )
    assert second == run
    assert run.awaits_run_id == first.run_id
    assert AgenticParameters.from_document(second_parameters).baseline_run_id == first.run_id


@pytest.mark.parametrize(
    ("rounds", "prompts", "transforms"),
    [(0, 20, ()), (6, 20, ()), (3, 51, ()), (3, 20, ("unknown",))],
)
def test_agentic_parameters_out_of_range_are_rejected(
    rounds: int, prompts: int, transforms: tuple[str, ...]
) -> None:
    """Rounds, prompt counts and transforms are checked before any run is queued."""
    use_case, store, _, queue = services()
    store.baselines.return_value = []
    with pytest.raises(ApplicationError):
        use_case.start_agentic(
            OWNER, "conn-1", rounds=rounds, prompts_per_round=prompts, transform_names=transforms
        )
    queue.enqueue.assert_not_called()


def test_an_attack_only_transform_is_kept_off_over_refusal_prompts() -> None:
    """Arabizi changes meaning, so an agentic run may choose it for attacks alone."""
    use_case, store, _, queue = services()
    store.baselines.return_value = [(baseline("base-1", RunStatus.COMPLETED), None)]
    use_case.start_agentic(
        OWNER, "conn-1", rounds=1, prompts_per_round=5, transform_names=("arabizi",)
    )
    queue.enqueue.assert_called_once()


def test_lifecycle_and_evidence_preserve_owner_scope() -> None:
    """Resume, cancellation and evidence use the authenticated owner."""
    use_case, _, _, queue = services()
    use_case.resume(OWNER, "run-1")
    use_case.cancel(OWNER, "run-1")
    use_case.outcome_page(OWNER, "run-1", 100, 50)
    queue.resume.assert_called_once_with("run-1", OWNER)
    queue.cancel.assert_called_once_with("run-1", OWNER)
    queue.outcome_page.assert_called_once_with("run-1", OWNER, 100, 50)


def test_an_agentic_run_pages_and_exports_its_generated_prompts() -> None:
    """An agentic run's evidence is its prompts, read with the owner's scope."""
    connections = Mock(spec=ManageConnections)
    store = Mock(spec=RunStore)
    store.get.return_value = run_of(RunKind.AGENTIC)
    store.get_report.return_value = {"kind": "agentic", "rounds": []}
    generated = Mock(spec=GeneratedEvidence)
    generated.prompt_documents.return_value = iter([{"prompt_id": "p-1"}])
    queue = Mock(spec=RunAdmission)
    queue.worker_available.return_value = True
    use_case = ManageRuns(store, connections, queue=queue, generated=generated)
    use_case.prompt_page(OWNER, "run-1", 0, 50)
    generated.prompt_page.assert_called_once_with("run-1", OWNER, 0, 50)
    exported = json.loads("".join(use_case.export_report(OWNER, "run-1")))
    assert exported["prompts"] == [{"prompt_id": "p-1"}]
    queue.outcome_documents.assert_not_called()


def test_inconsistent_evidence_page_cannot_loop_forever() -> None:
    """A stalled evidence source fails instead of yielding a partial export."""
    admission = cast(RunAdmission, Mock(spec=RunAdmission))
    cast(Mock, admission).outcome_page.return_value = {"items": [], "total": 1}
    with pytest.raises(ApplicationError, match="incomplete"):
        list(RunAdmission.outcome_documents(admission, "run-1", OWNER))
