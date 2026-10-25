"""Manage evaluation admission, lifecycle and stored reports."""

import json
import uuid
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from harass.application.connections import ManageConnections
from harass.application.evaluation.parameters import RunParameters
from harass.application.ports.run_admission import RunAdmission
from harass.application.ports.run_store import RunStore
from harass.domain.evaluation_run import EvaluationRun, RunStatus


class ManageRuns:
    """Coordinate verified connections and evaluation persistence."""

    def __init__(
        self,
        run_store: RunStore,
        connections: ManageConnections,
        *,
        queue: RunAdmission,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Bind query storage, verified connections and durable admission."""
        self._run_store = run_store
        self._connections = connections
        self._queue = queue
        self._clock = clock

    def resume(self, owner_id: str, run_id: str) -> EvaluationRun:
        """Resume suspended work from its durable checkpoint."""
        return self._queue.resume(run_id, owner_id)

    def outcome_page(
        self, owner_id: str, run_id: str, offset: int, limit: int
    ) -> dict[str, Any]:
        """Read a bounded page of owner-scoped attempt evidence."""
        return self._queue.outcome_page(run_id, owner_id, offset, limit)

    def export_report(self, owner_id: str, run_id: str) -> Iterator[str]:
        """Stream a complete report without loading all evidence."""
        document = {**self.get_report(owner_id, run_id)}
        document.pop("outcomes", None)
        yield json.dumps(document, ensure_ascii=False)[:-1] + ', "outcomes": ['
        separator = ""
        for record in self._queue.outcome_documents(run_id, owner_id):
            yield separator + json.dumps(record, ensure_ascii=False)
            separator = ","
        yield "]}"

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
                "started_at": run.started_at.isoformat()
                if run.started_at
                else None,
                "finished_at": run.finished_at.isoformat()
                if run.finished_at
                else None,
                "events": run.lifecycle_events,
            },
        }

    def list_for_owner(self, owner_id: str) -> list[EvaluationRun]:
        """Return the owner's runs, most recent first."""
        return self._run_store.list_for_owner(owner_id)

    def page_for_owner(
        self, owner_id: str, offset: int, limit: int
    ) -> tuple[list[EvaluationRun], dict[str, int]]:
        """Read history pages and aggregate owner-scoped status counts."""
        return self._run_store.page_for_owner(
            owner_id, offset, limit
        ), self._run_store.counts_for_owner(owner_id)

    def start(
        self, owner_id: str, connection_id: str, parameters: RunParameters
    ) -> EvaluationRun:
        """Create a pending run for a connection that passed its test.

        Raises: ConnectionNotReadyError: If the connection is untested or
        failed. UnknownConnectionError: If the owner has no such connection.
        """
        target = self._connections.target_for_evaluation(
            owner_id, connection_id
        )
        run = EvaluationRun(
            run_id=str(uuid.uuid4()),
            owner_id=owner_id,
            connection_id=connection_id,
            target_model=target.model_name,
            status=RunStatus.PENDING,
            created_at=self._clock(),
        )
        self._queue.enqueue(
            run,
            {
                **parameters.document(),
                "connection_revision": target.connection_revision,
            },
            target.base_url,
        )
        return run

    def cancel(self, owner_id: str, run_id: str) -> EvaluationRun:
        """Cancel owned work while preserving committed evidence."""
        return self._queue.cancel(run_id, owner_id)
