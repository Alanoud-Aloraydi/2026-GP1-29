"""Manage evaluation admission, lifecycle and stored reports."""

import json
import uuid
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from harass.application.connections import ManageConnections
from harass.application.errors import ApplicationError
from harass.application.evaluation.contracts import AgenticParameters, RunParameters
from harass.application.ports.generation import GeneratedEvidence
from harass.application.ports.runs import RunAdmission, RunStore
from harass.domain.case_selection import CaseSelection
from harass.domain.evaluation_run import EvaluationRun, RunKind, RunStatus
from harass.domain.generation.transforms import adapter_sequence, axis_transforms
from harass.domain.taxonomy import ArabicVariety, Axis

AGENTIC_AXES = (Axis.OVER_REFUSAL, Axis.ADVERSARIAL)


class ManageRuns:
    """Coordinate verified connections and evaluation persistence."""

    def __init__(
        self,
        run_store: RunStore,
        connections: ManageConnections,
        *,
        queue: RunAdmission,
        generated: GeneratedEvidence,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Bind query storage, connections, admission and generated evidence.

        ``generated`` reads the prompts that are an agentic run's evidence.
        """
        self._run_store = run_store
        self._connections = connections
        self._queue = queue
        self._generated = generated
        self._clock = clock

    def resume(self, owner_id: str, run_id: str) -> EvaluationRun:
        """Resume suspended work from its durable checkpoint."""
        return self._queue.resume(run_id, owner_id)

    def outcome_page(self, owner_id: str, run_id: str, offset: int, limit: int) -> dict[str, Any]:
        """Read a bounded page of a baseline run's owner-scoped attempt evidence."""
        return self._queue.outcome_page(run_id, owner_id, offset, limit)

    def prompt_page(self, owner_id: str, run_id: str, offset: int, limit: int) -> dict[str, Any]:
        """Read a bounded page of an agentic run's generated prompts with their replies."""
        return self._generated.prompt_page(run_id, owner_id, offset, limit)

    def export_report(self, owner_id: str, run_id: str) -> Iterator[str]:
        """Stream a complete report without loading all evidence.

        The report is read before streaming starts, so a missing or foreign run
        fails as an error response rather than halfway through a download.
        """
        document = {**self.get_report(owner_id, run_id)}
        document.pop("outcomes", None)
        if document.get("kind") == RunKind.AGENTIC:
            records = self._generated.prompt_documents(run_id, owner_id)
            return _report_chunks(document, "prompts", records)
        return _report_chunks(document, "outcomes", self._queue.outcome_documents(run_id, owner_id))

    def get(self, owner_id: str, run_id: str) -> EvaluationRun:
        """Read an owned run and the current worker availability."""
        run = self._run_store.get(run_id, owner_id)
        return replace(run, worker_available=self._queue.worker_available())

    def get_report(self, owner_id: str, run_id: str) -> dict[str, Any]:
        """Return the stored report document of the owner's completed run.

        Raises: UnknownRunError: If the run or its report does not exist for
        the owner.
        """
        run = self.get(owner_id, run_id)
        return {
            **self._run_store.get_report(run_id, owner_id),
            "lifecycle": {
                "created_at": run.created_at.isoformat(),
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "events": run.lifecycle_events,
            },
        }

    def page_for_owner(
        self, owner_id: str, offset: int, limit: int
    ) -> tuple[list[EvaluationRun], dict[str, int]]:
        """Read history pages and aggregate owner-scoped status counts."""
        return self._run_store.page_for_owner(
            owner_id, offset, limit
        ), self._run_store.counts_for_owner(owner_id)

    def start(self, owner_id: str, connection_id: str, parameters: RunParameters) -> EvaluationRun:
        """Create a pending baseline run for a connection that passed its test.

        Raises: ConnectionNotReadyError: If the connection is untested or
        failed. UnknownConnectionError: If the owner has no such connection.
        """
        return self._enqueue(owner_id, connection_id, RunKind.BASELINE, parameters.document())

    def start_agentic(
        self,
        owner_id: str,
        connection_id: str,
        *,
        axis: Axis | None = None,
        rounds: int,
        prompts_per_round: int,
        transform_names: tuple[str, ...] = (),
        varieties: frozenset[ArabicVariety] = frozenset(),
    ) -> EvaluationRun:
        """Create a pending agentic run on one axis, or both when ``axis`` is None.

        The run is seeded from the latest completed baseline run on the
        connection that covers its axes. Lacking one, it waits for an active
        baseline run that covers them, or for a new baseline run on its axes
        and varieties that is admitted first.

        Raises:
            ApplicationError: If the rounds, prompt count or transforms are invalid.
            ActiveRunError: If another run of the owner is active.
            ConnectionNotReadyError: If the connection is untested or failed.
            UnknownConnectionError: If the owner has no such connection.
        """
        axes = (axis,) if axis else AGENTIC_AXES
        baseline = self._baseline_for(owner_id, connection_id, axes, varieties)
        baseline_id = baseline.run_id if baseline else str(uuid.uuid4())
        try:
            for chosen in axes:
                adapter_sequence(axis_transforms(transform_names, chosen), chosen)
            parameters = AgenticParameters(
                baseline_id,
                axes=axes,
                rounds=rounds,
                prompts_per_round=prompts_per_round,
                transform_names=transform_names,
                varieties=varieties,
            )
        except ValueError as error:
            raise ApplicationError(str(error)) from None
        if baseline is None:
            selection = CaseSelection(axis=axis, varieties=varieties)
            self._enqueue(
                owner_id,
                connection_id,
                RunKind.BASELINE,
                RunParameters(selection).document(),
                run_id=baseline_id,
            )
        waits = baseline is None or baseline.status is not RunStatus.COMPLETED
        return self._enqueue(
            owner_id,
            connection_id,
            RunKind.AGENTIC,
            parameters.document(),
            awaits_run_id=baseline_id if waits else None,
        )

    def _baseline_for(
        self,
        owner_id: str,
        connection_id: str,
        axes: tuple[Axis, ...],
        varieties: frozenset[ArabicVariety],
    ) -> EvaluationRun | None:
        """Return the baseline run an agentic run on ``axes`` and ``varieties`` starts from.

        The latest completed covering baseline is preferred over one still
        running; None when no baseline covers the run.
        """
        covering = [
            run
            for run, selection in self._run_store.baselines(owner_id, connection_id)
            if _covers(selection, axes, varieties)
        ]
        completed = [run for run in covering if run.status is RunStatus.COMPLETED]
        return next(iter(completed or covering), None)

    def _enqueue(
        self,
        owner_id: str,
        connection_id: str,
        kind: RunKind,
        parameters: dict[str, Any],
        *,
        run_id: str | None = None,
        awaits_run_id: str | None = None,
    ) -> EvaluationRun:
        """Queue a pending run of one kind against a verified connection.

        ``run_id`` is chosen beforehand when another run already refers to it,
        and ``awaits_run_id`` names the baseline run an agentic run waits for.
        """
        target = self._connections.target_for_evaluation(owner_id, connection_id)
        run = EvaluationRun(
            run_id=run_id or str(uuid.uuid4()),
            owner_id=owner_id,
            connection_id=connection_id,
            target_model=target.model_name,
            status=RunStatus.PENDING,
            created_at=self._clock(),
            kind=kind,
            awaits_run_id=awaits_run_id,
        )
        self._queue.enqueue(
            run, {**parameters, "connection_revision": target.connection_revision}, target.base_url
        )
        return run

    def cancel(self, owner_id: str, run_id: str) -> EvaluationRun:
        """Cancel owned work while preserving committed evidence."""
        return self._queue.cancel(run_id, owner_id)


def _covers(
    selection: CaseSelection, axes: tuple[Axis, ...], varieties: frozenset[ArabicVariety]
) -> bool:
    """Return whether a baseline's selection fits an agentic run on ``axes`` and ``varieties``.

    The baseline seeds the run's cards and gives its comparison rate, so its
    varieties must be exactly the run's: a baseline on more varieties would
    mix others into both. A baseline limited to one axis covers only a run
    on that axis, and one narrowed by domain, risk or strategy covers none.
    An empty variety set means every variety on either side.
    """
    if selection.subject_domains or selection.risk_categories or selection.strategies:
        return False
    if selection.axis is not None and (selection.axis,) != axes:
        return False
    return (selection.varieties or frozenset(ArabicVariety)) == (
        varieties or frozenset(ArabicVariety)
    )


def _report_chunks(
    document: dict[str, Any], key: str, records: Iterator[dict[str, Any]]
) -> Iterator[str]:
    """Yield the summary, then the stored evidence one record at a time."""
    yield json.dumps(document, ensure_ascii=False)[:-1] + f', "{key}": ['
    separator = ""
    for record in records:
        yield separator + json.dumps(record, ensure_ascii=False)
        separator = ","
    yield "]}"
