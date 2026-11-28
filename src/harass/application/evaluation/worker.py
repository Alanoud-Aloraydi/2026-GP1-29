"""Renewable worker execution outside the HTTP application lifecycle."""

import asyncio
import logging
import uuid
from typing import Any

from harass.application.connections import ManageConnections
from harass.application.errors import ApplicationError
from harass.application.evaluation.contracts import (
    AgenticParameters,
    EvaluationRequest,
    RunParameters,
)
from harass.application.evaluation.runner import RunEvaluation
from harass.application.generation.agentic_run import (
    AgenticNoMeasurementError,
    AgenticNoVerdictError,
    RunAgenticEvaluation,
)
from harass.application.ports.runs import (
    EvaluationSuspendedError,
    EvaluationYieldedError,
    LeaseLostError,
    RunJob,
    RunQueue,
    StorageUnavailableError,
)
from harass.application.reporting.document import report_document
from harass.domain.evaluation_run import RunKind
from harass.domain.target_connection import TargetConnection

logger = logging.getLogger(__name__)


class AgenticUnavailableError(ApplicationError):
    """The worker has no generator models, so it cannot play an agentic run."""


class ProcessRuns:
    """Execute judge-owned work with durable recovery."""

    def __init__(
        self,
        queue: RunQueue,
        connections: ManageConnections,
        evaluation: RunEvaluation,
        agentic: RunAgenticEvaluation | None,
        *,
        heartbeat_seconds: float = 20,
        poll_seconds: float = 2,
    ) -> None:
        """Inject execution ports and bounded worker scheduling intervals.

        ``agentic`` is None when the generator models are not configured;
        an agentic run then fails with a message saying so.
        """
        self._queue = queue
        self._connections = connections
        self._evaluation = evaluation
        self._agentic = agentic
        self._heartbeat_seconds = heartbeat_seconds
        self._poll_seconds = poll_seconds

    async def once(self) -> bool:
        """Process one claimed job when the judge slot is available."""
        await asyncio.to_thread(self._queue.heartbeat)
        job = await asyncio.to_thread(self._queue.claim, str(uuid.uuid4()))
        if job is None:
            return False
        task = asyncio.create_task(self._execute(job))
        try:
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=self._heartbeat_seconds)
                if not done:
                    await asyncio.to_thread(self._queue.heartbeat)
                    await asyncio.to_thread(self._queue.renew, job)
            await task
        except (LeaseLostError, StorageUnavailableError):
            logger.warning(
                "Run %s suspended because its lease or storage is unavailable", job.run.run_id
            )
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            try:
                await asyncio.to_thread(self._queue.release, job)
            except StorageUnavailableError:
                logger.warning("Run %s lease will expire for recovery", job.run.run_id)
        return True

    async def _execute(self, job: RunJob) -> None:
        """Validate immutable job inputs and persist its execution outcome."""
        try:
            target = self._queued_target(job)
            document = await self._report(job, target)
            document["target_endpoint"] = target.base_url
            document["evidence_paged"] = True
            await asyncio.to_thread(self._queue.finish, job, document)
        except (LeaseLostError, StorageUnavailableError):
            raise
        except EvaluationYieldedError:
            return
        except EvaluationSuspendedError as error:
            await asyncio.to_thread(self._queue.fail, job, str(error), resumable=True)
        except (AgenticUnavailableError, AgenticNoVerdictError, AgenticNoMeasurementError) as error:
            # Resuming cannot change any of these outcomes, so the failure is final.
            await asyncio.to_thread(self._queue.fail, job, str(error))
        except Exception as error:
            logger.error("Run %s failed: %s", job.run.run_id, type(error).__name__)
            await asyncio.to_thread(
                self._queue.fail, job, f"Evaluation failed: {type(error).__name__}."
            )

    async def _report(self, job: RunJob, target: TargetConnection) -> dict[str, Any]:
        """Play the job's next share of work by its kind and return its report."""
        journal = self._queue.journal(job)
        if job.run.kind is RunKind.AGENTIC:
            if self._agentic is None:
                raise AgenticUnavailableError("Agentic generation is not configured.")
            return await self._agentic.execute(
                target,
                AgenticParameters.from_document(job.parameters),
                job.run.run_id,
                job.run.owner_id,
                journal,
            )
        parameters = RunParameters.from_document(job.parameters)
        report = await self._evaluation.execute(
            EvaluationRequest(target, parameters, job.run.run_id), journal=journal
        )
        document = await asyncio.to_thread(report_document, report, include_outcomes=False)
        # The report shows the settings the run was played with, as the agentic report does.
        document["parameters"] = parameters.document()
        return document

    def _queued_target(self, job: RunJob) -> TargetConnection:
        """Load the run's connection and refuse it if it changed since."""
        target = self._connections.target_for_evaluation(job.run.owner_id, job.run.connection_id)
        if target.base_url != job.target_endpoint or target.model_name != job.run.target_model:
            raise ValueError("The queued target connection changed.")
        revision = job.connection_revision
        if revision is not None and target.connection_revision != revision:
            raise ValueError("The queued target connection revision changed.")
        return target

    async def serve(self) -> None:
        """Poll for work while preserving recoverable checkpoints."""
        while True:
            try:
                available = await self.once()
            except StorageUnavailableError:
                available = False
                logger.warning("Run storage unavailable; worker will retry admission")
            if not available:
                await asyncio.sleep(self._poll_seconds)
