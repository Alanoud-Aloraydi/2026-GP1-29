"""Send each dataset case once as written, with durable attempt reservations."""

import asyncio
import hashlib
import json
from dataclasses import asdict
from typing import Any

from harass.application.evaluation.outcome_codec import read_outcome
from harass.application.ports.evaluation import AttemptExecutor, EvaluationEngine, EvaluationJournal
from harass.application.ports.runs import EvaluationSuspendedError, EvaluationYieldedError
from harass.application.reporting.document import outcome_document
from harass.domain.case_outcome import CaseOutcome
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.evaluation_plan import EvaluationPlan
from harass.domain.target_connection import TargetConnection

INTERRUPTED_ATTEMPT = "Attempt interrupted before verdict commit."
TECHNICAL_FAILURE_LIMIT = 3


class BaselineEngine(EvaluationEngine):
    """Send every planned case once and commit each judged attempt."""

    def __init__(self, executor: AttemptExecutor, *, quantum_attempts: int = 50) -> None:
        """Inject the one-attempt executor and the worker's fair-share quantum."""
        if quantum_attempts < 1:
            raise ValueError("Worker quantum must be positive.")
        self._executor = executor
        self._quantum_attempts = quantum_attempts

    async def evaluate(
        self,
        plan: EvaluationPlan,
        target: TargetConnection,
        run_identifier: str,
        *,
        journal: EvaluationJournal | None = None,
    ) -> list[CaseOutcome]:
        """Evaluate the plan's cases in order, resuming from the journal.

        An attempt reserved before a crash is committed as uncertain instead
        of being sent again, so the model never receives one case twice.
        """
        state = await _initial_state(plan, target, journal)
        outcomes: list[CaseOutcome] = []
        committed = 0
        while state["case_index"] < len(plan.cases):
            case = plan.cases[state["case_index"]]
            pending = state["pending"]
            if pending:
                outcome = read_outcome(pending)
            else:
                outcome = await self._submit(case, target, run_identifier, state, journal)
            state = _advance(state, outcome)
            if journal is None:
                outcomes.append(outcome)
                continue
            await asyncio.to_thread(journal.commit, outcome, state)
            if not pending:
                committed += 1
                self._pause_if_needed(state, committed, len(plan.cases))
        if journal is None:
            return outcomes
        return await asyncio.to_thread(lambda: list(journal.outcomes(lightweight=True)))

    async def _submit(
        self,
        case: EvaluationCase,
        target: TargetConnection,
        run_identifier: str,
        state: dict[str, Any],
        journal: EvaluationJournal | None,
    ) -> CaseOutcome:
        """Reserve the attempt before the external request is made."""
        if journal:
            reservation = CaseOutcome(case, error=INTERRUPTED_ATTEMPT, submission_uncertain=True)
            reserved = {**state, "pending": outcome_document(reservation)}
            await asyncio.to_thread(journal.reserve, reserved)
        return await self._executor.execute(case, case.prompt_text, target, run_identifier)

    def _pause_if_needed(self, state: dict[str, Any], committed: int, case_count: int) -> None:
        """Suspend on repeated failures or yield after a full quantum."""
        if state["technical_failures"] >= TECHNICAL_FAILURE_LIMIT:
            raise EvaluationSuspendedError(
                "Target or judge repeatedly unavailable; saved progress can be resumed."
            )
        if committed >= self._quantum_attempts and state["case_index"] < case_count:
            raise EvaluationYieldedError("Committed work yielded the judge slot.")


async def _initial_state(
    plan: EvaluationPlan, target: TargetConnection, journal: EvaluationJournal | None
) -> dict[str, Any]:
    """Resume the journal checkpoint or start at the first case."""
    saved = (
        await asyncio.to_thread(journal.initialize, _fingerprint(plan, target), len(plan.cases))
        if journal
        else {}
    )
    return {"case_index": 0, "pending": None, "technical_failures": 0, **saved}


def _advance(state: dict[str, Any], outcome: CaseOutcome) -> dict[str, Any]:
    """Move to the next case, counting consecutive technical failures."""
    failures = state["technical_failures"] + 1 if outcome.technical_error else 0
    return {"case_index": state["case_index"] + 1, "pending": None, "technical_failures": failures}


def _fingerprint(plan: EvaluationPlan, target: TargetConnection) -> str:
    """Bind a checkpoint to its evaluation plan and target identity."""
    digest = hashlib.sha256()
    for chunk in json.JSONEncoder(sort_keys=True).iterencode(asdict(plan)):
        digest.update(chunk.encode("utf-8"))
    digest.update(target.base_url.encode("utf-8"))
    digest.update(target.model_name.encode("utf-8"))
    return digest.hexdigest()
