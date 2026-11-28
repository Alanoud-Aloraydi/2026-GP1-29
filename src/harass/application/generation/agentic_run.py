"""Run the agentic generator against a client's model as one durable evaluation run.

An agentic run seeds the target's pattern cards from its baseline run, then
plays the chosen number of rounds, each writing prompts on every chosen
axis. Every round on one axis is a unit of work: the checkpoint is saved before a unit
starts and after it ends, and the worker yields its slot between units, so
a long run shares the judge with other clients and resumes where it stopped.
A unit interrupted after it stored prompts is not played again, since they
may have reached the target already, and what it stored stays in the report;
one interrupted before it stored any is played again, as nothing was sent.
A run whose measurement round reached no verdict on an axis fails, since its
rates could not be compared with the baseline's.
"""

import asyncio
import hashlib
import json
from collections import Counter
from typing import Any

from harass.application.errors import ApplicationError
from harass.application.evaluation.contracts import AgenticParameters
from harass.application.generation.contracts import GenerationRequest
from harass.application.generation.generation_service import GenerateRound
from harass.application.generation.seeding import SeedFromBaseline
from harass.application.ports.evaluation import EvaluationJournal
from harass.application.ports.generation import GenerationStore
from harass.application.ports.runs import EvaluationSuspendedError, EvaluationYieldedError, RunStore
from harass.application.reporting.agentic_document import agentic_document
from harass.domain.generation.transforms import axis_transforms
from harass.domain.target_connection import TargetConnection
from harass.domain.taxonomy import Axis

# Rounds in a row that reach no verdict suspend the run: the target is down.
SILENT_ROUND_LIMIT = 2
# The stored failures start with these codes so the report page can explain them.
NO_VERDICT_CODE = "agentic_no_verdict"
NO_MEASUREMENT_CODE = "agentic_no_measurement"
# Stored prompts that failed the review or safety gates, and valid ones left unjudged.
FAILED_GATES = "failed_gates"
UNJUDGED = "unjudged"


class AgenticNoVerdictError(ApplicationError):
    """Every round of an agentic run ended without one judged request.

    The message holds only classified reason codes and their counts, never
    model or provider text, so it is safe to store and show.
    """

    def __init__(self, reasons: Counter[str]) -> None:
        """Format the reasons as ``code: reason=count, ...`` in a stable order."""
        counts = ", ".join(f"{reason}={count}" for reason, count in sorted(reasons.items()))
        super().__init__(f"{NO_VERDICT_CODE}: {counts}" if counts else NO_VERDICT_CODE)


class AgenticNoMeasurementError(ApplicationError):
    """A chosen axis has no judged request in its measurement round.

    Its discovery rates may exist, but without the unbiased measurement the
    run cannot be compared with its baseline, so it must not complete. The
    message names only axis codes.
    """

    def __init__(self, axes: list[str]) -> None:
        """Format the axes as ``code: AT, OR``."""
        super().__init__(f"{NO_MEASUREMENT_CODE}: {', '.join(axes)}")


class RunAgenticEvaluation:
    """Play an agentic run's rounds under the worker's journal."""

    def __init__(
        self,
        rounds: GenerateRound,
        seeding: SeedFromBaseline,
        store: GenerationStore,
        runs: RunStore,
    ) -> None:
        """Bind the round engine, the seeding step and the stores the report reads."""
        self._rounds = rounds
        self._seeding = seeding
        self._store = store
        self._runs = runs

    async def execute(
        self,
        target: TargetConnection,
        parameters: AgenticParameters,
        run_id: str,
        owner_id: str,
        journal: EvaluationJournal,
    ) -> dict[str, Any]:
        """Play the next unit of the run, or report the run once all are played.

        Raises:
            EvaluationYieldedError: After a unit, while units remain.
            EvaluationSuspendedError: When rounds in a row reach no verdict.
            AgenticNoVerdictError: When the whole run judged no request.
            AgenticNoMeasurementError: When an axis's measurement round judged none.
        """
        units = parameters.rounds * len(parameters.axes)
        saved = await asyncio.to_thread(journal.initialize, _fingerprint(parameters, target), units)
        state: dict[str, Any] = {
            "case_index": 0,
            "seeded_cards": None,
            "pending": False,
            "silent_rounds": 0,
            "learned": [],
            **saved,
        }
        if state["seeded_cards"] is None:
            seeded = await self._seeding.seed(
                target.model_name, owner_id, parameters.baseline_run_id, parameters.axes
            )
            state = {**state, "seeded_cards": seeded}
            await asyncio.to_thread(journal.reserve, state)
            raise EvaluationYieldedError("Seeding yielded the judge slot.")
        if state["case_index"] < units:
            state = await self._play(target, parameters, run_id, state, journal)
            if state["silent_rounds"] >= SILENT_ROUND_LIMIT:
                raise EvaluationSuspendedError(
                    "Target or judge repeatedly unavailable; saved progress can be resumed."
                )
            if state["case_index"] < units:
                raise EvaluationYieldedError("A finished round yielded the judge slot.")
        document = await asyncio.to_thread(
            self._report, target.model_name, parameters, run_id, owner_id, state
        )
        if not _judged(document):
            raise AgenticNoVerdictError(_no_verdict_reasons(document))
        unmeasured = [
            axis for axis, rates in document["axes"].items() if not rates["measurement"]["total"]
        ]
        if unmeasured:
            raise AgenticNoMeasurementError(unmeasured)
        return document

    async def _play(
        self,
        target: TargetConnection,
        parameters: AgenticParameters,
        run_id: str,
        state: dict[str, Any],
        journal: EvaluationJournal,
    ) -> dict[str, Any]:
        """Play one unit and return the checkpoint that follows it."""
        unit = state["case_index"]
        axes = parameters.axes
        round_index, axis = unit // len(axes), axes[unit % len(axes)]
        entry: dict[str, Any] = {
            "axis": str(axis),
            "round": round_index,
            "lessons": 0,
            "cards": 0,
            "dropped": {},
        }
        silent = state["silent_rounds"]
        stored = state["pending"] and await asyncio.to_thread(
            self._unit_stored, target.model_name, axis, run_id, round_index
        )
        if stored:
            entry["interrupted"] = True
        else:
            await asyncio.to_thread(journal.reserve, {**state, "pending": True})
            report = await self._rounds.execute(
                GenerationRequest(
                    target,
                    axis=axis,
                    round_index=round_index,
                    count=parameters.prompts_per_round,
                    run_identifier=run_id,
                    transform_names=axis_transforms(parameters.transform_names, axis),
                    varieties=parameters.varieties,
                )
            )
            valid = sum(prompt.is_valid for prompt in report.prompts)
            silent = silent + 1 if valid and not report.outcomes else 0
            entry.update(
                lessons=len(report.lessons),
                cards=len(report.cards),
                dropped={str(reason): count for reason, count in report.dropped.items()},
                interrupted=False,
            )
        following = {
            **state,
            "case_index": unit + 1,
            "pending": False,
            "silent_rounds": silent,
            "learned": [*state["learned"], entry],
        }
        await asyncio.to_thread(journal.reserve, following)
        return following

    def _unit_stored(self, target_model: str, axis: Axis, run_id: str, round_index: int) -> bool:
        """Return whether a unit stored any prompt, which may have reached the target.

        Prompts are stored before any request is sent, so a unit with none
        sent nothing and can be played again. O(n) in the axis's prompts.
        """
        history = self._store.history(target_model, axis)
        return any(
            prompt.run_id == run_id and prompt.round_index == round_index
            for prompt in history.prompts
        )

    def _report(
        self,
        target_model: str,
        parameters: AgenticParameters,
        run_id: str,
        owner_id: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the run's report from its stored prompts and the baseline's rates."""
        baseline = self._runs.get_report(parameters.baseline_run_id, owner_id)
        return agentic_document(
            run_id,
            target_model,
            parameters,
            [self._store.history(target_model, axis) for axis in parameters.axes],
            state["learned"],
            baseline.get("metrics", {}),
            state["seeded_cards"],
        )


def _judged(document: dict[str, Any]) -> int:
    """Count the requests judged across every axis and phase of the run."""
    return sum(
        rates[phase]["total"]
        for rates in document["axes"].values()
        for phase in ("measurement", "discovery")
    )


def _no_verdict_reasons(document: dict[str, Any]) -> Counter[str]:
    """Sum why each round reached no verdict: drops, gate failures and unjudged prompts.

    O(r * d) for r rounds and d drop reasons per round.
    """
    reasons: Counter[str] = Counter()
    for entry in document["rounds"]:
        reasons.update(entry["dropped"])
        reasons[FAILED_GATES] += entry["prompts"] - entry["valid"]
        reasons[UNJUDGED] += entry["valid"]
    return Counter({reason: count for reason, count in reasons.items() if count})


def _fingerprint(parameters: AgenticParameters, target: TargetConnection) -> str:
    """Bind a checkpoint to the run's parameters and target identity."""
    digest = hashlib.sha256(json.dumps(parameters.document(), sort_keys=True).encode())
    digest.update(target.base_url.encode("utf-8"))
    digest.update(target.model_name.encode("utf-8"))
    return digest.hexdigest()
