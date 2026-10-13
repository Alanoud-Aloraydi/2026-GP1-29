"""Use case: start evaluation runs, track their status and keep their reports."""

import json
import logging
import uuid
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from harass.application.evaluation_report import EvaluationRequest
from harass.application.ports.run_queue import RunQueue
from harass.application.ports.run_store import RunStore
from harass.application.report_document import report_document
from harass.application.use_cases.manage_connections import ManageConnections
from harass.application.use_cases.run_evaluation import RunEvaluation
from harass.domain.case_selection import CaseSelection
from harass.domain.evaluation_run import EvaluationRun, RunStatus
from harass.domain.prompt_variant import AdaptiveSettings, VariantSelection

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunParameters:
    """What a client chose for a run, besides which connection to evaluate."""

    selection: CaseSelection = field(default_factory=CaseSelection)
    include_baseline: bool = True
    max_base_cases_per_axis: int | None = None
    sampling_seed: int = 0
    variant_selection: VariantSelection = field(default_factory=VariantSelection)
    adaptive_settings: AdaptiveSettings = field(default_factory=AdaptiveSettings)

    def document(self) -> dict[str, Any]:
        """Return JSON-compatible job inputs without any target credentials."""
        document = asdict(self)
        document["selection"] = {
            key: sorted(value) if isinstance(value, frozenset) else value
            for key, value in document["selection"].items()
        }
        return document


class ManageRuns:
    """Starts a run against a verified connection, then records its progress and report."""

    def __init__(
        self,
        run_store: RunStore,
        connections: ManageConnections,
        evaluation: RunEvaluation | None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        *,
        queue: RunQueue | None = None,
    ) -> None:
        """Store the ports and the clock used to time-stamp runs."""
        self._run_store = run_store
        self._connections = connections
        self._evaluation = evaluation
        self._clock = clock
        self._queue = queue

    @property
    def durable(self) -> bool:
        """Return whether runs are admitted to an external worker queue."""
        return self._queue is not None

    def resume(self, owner_id: str, run_id: str) -> EvaluationRun:
        """Resume durable suspended work while preserving its original execution protocol."""
        if self._queue is None:
            raise RuntimeError("This run has no durable checkpoint.")
        return self._queue.resume(run_id, owner_id)

    def outcome_page(self, owner_id: str, run_id: str, offset: int, limit: int) -> dict[str, Any]:
        """Return owner-scoped evidence without loading a durable run's full report."""
        if self._queue is not None:
            return self._queue.outcome_page(run_id, owner_id, offset, limit)
        outcomes = self.get_report(owner_id, run_id)["outcomes"]
        return {
            "total": len(outcomes),
            "offset": offset,
            "limit": limit,
            "items": outcomes[offset : offset + limit],
        }

    def export_report(self, owner_id: str, run_id: str) -> Iterator[str]:
        """Stream a complete research report without assembling every transcript in memory."""
        document = {**self.get_report(owner_id, run_id)}
        outcomes = document.pop("outcomes", [])
        yield json.dumps(document, ensure_ascii=False)[:-1] + ', "outcomes": ['
        separator = ""
        records = (
            self._queue.outcome_documents(run_id, owner_id) if self._queue else iter(outcomes)
        )
        for record in records:
            yield separator + json.dumps(record, ensure_ascii=False)
            separator = ","
        yield "]}"

    def get(self, owner_id: str, run_id: str) -> EvaluationRun:
        """Return the owner's run.

        Raises:
            UnknownRunError: If the owner has no run with that identifier.
        """
        run = self._run_store.get(run_id, owner_id)
        return (
            replace(run, worker_available=self._queue.worker_available()) if self._queue else run
        )

    def get_report(self, owner_id: str, run_id: str) -> dict[str, Any]:
        """Return the stored report document of the owner's completed run.

        Raises:
            UnknownRunError: If the run or its report does not exist for the owner.
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

    def list_for_owner(self, owner_id: str) -> list[EvaluationRun]:
        """Return the owner's runs, most recent first."""
        return self._run_store.list_for_owner(owner_id)

    def page_for_owner(
        self, owner_id: str, offset: int, limit: int
    ) -> tuple[list[EvaluationRun], dict[str, int]]:
        """Read a bounded history page and aggregate counts for the whole account."""
        return self._run_store.page_for_owner(
            owner_id, offset, limit
        ), self._run_store.counts_for_owner(owner_id)

    def start(self, owner_id: str, connection_id: str, parameters: RunParameters) -> EvaluationRun:
        """Create a pending run for a connection that passed its test.

        Raises:
            ConnectionNotReadyError: If the connection is untested or failed.
            UnknownConnectionError: If the owner has no such connection.
        """
        target = self._connections.target_for_evaluation(owner_id, connection_id)
        run = EvaluationRun(
            run_id=str(uuid.uuid4()),
            owner_id=owner_id,
            connection_id=connection_id,
            target_model=target.model_name,
            status=RunStatus.PENDING,
            created_at=self._clock(),
        )
        if self._queue is None:
            self._run_store.create(run)
        else:
            self._queue.enqueue(
                run,
                {**parameters.document(), "connection_revision": target.connection_revision},
                target.base_url,
            )
        return run

    def cancel(self, owner_id: str, run_id: str) -> EvaluationRun:
        """Cancel pending or active work without removing committed evidence."""
        if self._queue is None:
            raise RuntimeError("Cancellation requires durable execution.")
        return self._queue.cancel(run_id, owner_id)

    async def execute(self, run: EvaluationRun, parameters: RunParameters) -> EvaluationRun:
        """Run the evaluation to completion, recording running, then completed or failed."""
        self._run_store.update(replace(run, status=RunStatus.RUNNING))
        try:
            if self._evaluation is None:
                raise RuntimeError("Queued runs require the external worker.")
            target = self._connections.target_for_evaluation(run.owner_id, run.connection_id)
            report = await self._evaluation.execute(
                EvaluationRequest(
                    target=target,
                    selection=parameters.selection,
                    include_baseline=parameters.include_baseline,
                    max_base_cases_per_axis=parameters.max_base_cases_per_axis,
                    sampling_seed=parameters.sampling_seed,
                    variant_selection=parameters.variant_selection,
                    adaptive_settings=parameters.adaptive_settings,
                    run_identifier=run.run_id,
                )
            )
            document = report_document(report)
            document["target_endpoint"] = target.base_url
            self._run_store.save_report(run.run_id, document)
            finished = replace(
                run,
                target_model=report.target_model,
                status=RunStatus.COMPLETED,
                finished_at=self._clock(),
            )
        except Exception as error:
            logger.error("Run %s failed: %s", run.run_id, type(error).__name__)
            finished = replace(
                run,
                status=RunStatus.FAILED,
                finished_at=self._clock(),
                error=f"Evaluation failed: {type(error).__name__}.",
            )
        self._run_store.update(finished)
        return finished
