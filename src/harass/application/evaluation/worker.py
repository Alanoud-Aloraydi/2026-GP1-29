"""Renewable worker execution outside the HTTP application lifecycle."""

import asyncio
import logging
import uuid

from harass.application.connections import ManageConnections
from harass.application.evaluation.contracts import EvaluationRequest
from harass.application.evaluation.job_parameters import read_run_parameters
from harass.application.evaluation.runner import RunEvaluation
from harass.application.ports.run_queue import (
    EvaluationSuspendedError,
    EvaluationYieldedError,
    LeaseLostError,
    RunJob,
    RunQueue,
    StorageUnavailableError,
)
from harass.application.reporting.document import report_document

logger = logging.getLogger(__name__)


class ProcessRuns:
    """Execute judge-owned work with durable recovery."""

    def __init__(
        self,
        queue: RunQueue,
        connections: ManageConnections,
        evaluation: RunEvaluation,
        *,
        heartbeat_seconds: float = 20,
        poll_seconds: float = 2,
    ) -> None:
        """Inject execution ports and bounded worker scheduling intervals."""
        self._queue, self._connections, self._evaluation = (
            queue,
            connections,
            evaluation,
        )
        self._heartbeat_seconds, self._poll_seconds = (
            heartbeat_seconds,
            poll_seconds,
        )

    async def once(self) -> bool:
        """Process one claimed job when the judge slot is available."""
        await asyncio.to_thread(self._queue.heartbeat)
        job = await asyncio.to_thread(self._queue.claim, str(uuid.uuid4()))
        if job is None:
            return False
        task = asyncio.create_task(self._execute(job))
        try:
            while not task.done():
                done, _ = await asyncio.wait(
                    {task}, timeout=self._heartbeat_seconds
                )
                if not done:
                    await asyncio.to_thread(self._queue.heartbeat)
                    await asyncio.to_thread(self._queue.renew, job)
            await task
        except (LeaseLostError, StorageUnavailableError):
            logger.warning(
                "Run %s suspended because its lease or storage is unavailable",
                job.run.run_id,
            )
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            try:
                await asyncio.to_thread(self._queue.release, job)
            except StorageUnavailableError:
                logger.warning(
                    "Run %s lease will expire for recovery", job.run.run_id
                )
        return True

    async def _execute(self, job: RunJob) -> None:
        """Validate immutable job inputs and persist its execution outcome."""
        try:
            target = self._connections.target_for_evaluation(
                job.run.owner_id, job.run.connection_id
            )
            if (
                target.base_url != job.target_endpoint
                or target.model_name != job.run.target_model
            ):
                raise ValueError("The queued target connection changed.")
            if (
                job.connection_revision is not None
                and target.connection_revision != job.connection_revision
            ):
                raise ValueError(
                    "The queued target connection revision changed."
                )
            parameters = read_run_parameters(job.parameters)
            report = await self._evaluation.execute(
                EvaluationRequest(
                    target=target,
                    selection=parameters.selection,
                    include_baseline=parameters.include_baseline,
                    max_base_cases_per_axis=parameters.max_base_cases_per_axis,
                    sampling_seed=parameters.sampling_seed,
                    variant_selection=parameters.variant_selection,
                    adaptive_settings=parameters.adaptive_settings,
                    run_identifier=job.run.run_id,
                ),
                journal=self._queue.journal(job),
            )
            document = await asyncio.to_thread(
                report_document, report, include_outcomes=False
            )
            document["target_endpoint"] = target.base_url
            document["evidence_paged"] = True
            await asyncio.to_thread(self._queue.finish, job, document)
        except (LeaseLostError, StorageUnavailableError):
            raise
        except EvaluationYieldedError:
            return
        except EvaluationSuspendedError as error:
            await asyncio.to_thread(
                self._queue.fail, job, str(error), resumable=True
            )
        except Exception as error:
            logger.error(
                "Run %s failed: %s", job.run.run_id, type(error).__name__
            )
            await asyncio.to_thread(
                self._queue.fail,
                job,
                f"Evaluation failed: {type(error).__name__}.",
            )

    async def serve(self) -> None:
        """Poll for work while preserving recoverable checkpoints."""
        while True:
            try:
                available = await self.once()
            except StorageUnavailableError:
                available = False
                logger.warning(
                    "Run storage unavailable; worker will retry admission"
                )
            if not available:
                await asyncio.sleep(self._poll_seconds)
