"""Execute adaptive evaluations with durable attempt reservations."""

import asyncio
import hashlib
import json
from dataclasses import asdict, replace
from typing import Any

from harass.application.errors import EvaluationEngineError
from harass.application.evaluation.outcome_codec import read_outcome
from harass.application.ports.attempt_executor import AttemptExecutor
from harass.application.ports.evaluation_engine import EvaluationEngine
from harass.application.ports.evaluation_journal import EvaluationJournal
from harass.application.ports.run_queue import (
    EvaluationSuspendedError,
    EvaluationYieldedError,
)
from harass.application.ports.variant_catalog import VariantCatalog
from harass.application.reporting.document import outcome_document
from harass.domain.adaptive_controller import ThompsonController
from harass.domain.case_outcome import CaseOutcome
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.evaluation_plan import EvaluationPlan
from harass.domain.prompt_variant import (
    EvaluationMode,
    PromptVariant,
    VariantSelection,
)
from harass.domain.target_connection import TargetConnection
from harass.domain.taxonomy import Axis, ResponseCategory


class VariantEvaluationEngine(EvaluationEngine):
    """Checkpoint serial attempts and their adaptive feedback."""

    def __init__(
        self,
        catalog: VariantCatalog,
        executor: AttemptExecutor,
        *,
        quantum_attempts: int = 50,
    ) -> None:
        """Inject the library and one-attempt execution port."""
        self._catalog = catalog
        self._executor = executor
        if quantum_attempts < 1:
            raise ValueError("Worker quantum must be positive.")
        self._quantum_attempts = quantum_attempts

    async def evaluate(
        self,
        plan: EvaluationPlan,
        target: TargetConnection,
        run_identifier: str,
        *,
        journal: EvaluationJournal | None = None,
    ) -> list[CaseOutcome]:
        """Evaluate case recipes and recover uncertain submissions."""
        selection = plan.variant_selection or VariantSelection((), ())
        self._require_recipes(plan, selection)
        state = await _initial_state(plan, target, journal)
        controller = ThompsonController(plan.adaptive_settings.random_seed)
        if state.get("controller"):
            controller.restore(state["controller"])
        outcomes: list[CaseOutcome] = []
        committed = 0
        cached_index = -1
        variants: list[PromptVariant] = []
        while state["case_index"] < len(plan.cases):
            case = plan.cases[state["case_index"]]
            if cached_index != state["case_index"]:
                variants = self._catalog.variants(case, selection)
                cached_index = state["case_index"]
            recovered = bool(state.get("pending"))
            if recovered:
                outcome = read_outcome(state["pending"])
            else:
                used = state["used_variants"]
                remaining = [v for v in variants if v.variant_id not in used]
                baseline = plan.include_baseline and not state["baseline_done"]
                if not baseline and not remaining:
                    state = _next_case(state, controller)
                    if journal:
                        await asyncio.to_thread(journal.reserve, state)
                    continue
                reservation = _choose_attempt(
                    plan, case, remaining, baseline, state, controller
                )
                outcome, state = await self._submit(
                    reservation,
                    target,
                    run_identifier,
                    state,
                    controller,
                    journal,
                )
            outcome, state = _complete(
                outcome, state, variants, plan, controller
            )
            if journal is None:
                outcomes.append(outcome)
                continue
            await asyncio.to_thread(journal.commit, outcome, state)
            if not recovered:
                committed += 1
                self._pause_if_needed(state, committed, len(plan.cases))
        if journal is None:
            return outcomes
        return await asyncio.to_thread(
            lambda: list(journal.outcomes(lightweight=True))
        )

    def _require_recipes(
        self, plan: EvaluationPlan, selection: VariantSelection
    ) -> None:
        """Reject a plan in which some case would have nothing to send."""
        if plan.include_baseline:
            return
        for case in plan.cases:
            if not self._catalog.variants(case, selection):
                raise EvaluationEngineError(
                    "A selected case has no eligible variants or baseline."
                )

    def _pause_if_needed(
        self, state: dict[str, Any], committed: int, case_count: int
    ) -> None:
        """Suspend on repeated failures or yield after a full quantum."""
        if state.get("technical_failures", 0) >= 3:
            raise EvaluationSuspendedError(
                "Target or judge repeatedly unavailable; saved "
                "progress can be resumed."
            )
        unfinished = state["case_index"] < case_count
        if committed >= self._quantum_attempts and unfinished:
            raise EvaluationYieldedError(
                "Committed work yielded the judge slot."
            )

    async def _submit(
        self,
        reservation: CaseOutcome,
        target: TargetConnection,
        run_identifier: str,
        state: dict[str, Any],
        controller: ThompsonController,
        journal: EvaluationJournal | None,
    ) -> tuple[CaseOutcome, dict[str, Any]]:
        """Reserve submission intent before invoking the isolated attempt."""
        state = {
            **state,
            "controller": controller.snapshot(),
            "pending": outcome_document(reservation),
        }
        if journal:
            await asyncio.to_thread(journal.reserve, state)
        assert reservation.variant is not None
        outcome = await self._executor.execute(
            reservation.case, reservation.variant, target, run_identifier
        )
        return replace(
            outcome,
            variant=reservation.variant,
            attempt_number=reservation.attempt_number,
            posterior_before=reservation.posterior_before,
        ), state


def _choose_attempt(
    plan: EvaluationPlan,
    case: EvaluationCase,
    remaining: list[PromptVariant],
    baseline: bool,
    state: dict[str, Any],
    controller: ThompsonController,
) -> CaseOutcome:
    """Select a recipe and retain its pre-observation controller parameters."""
    context = f"{case.axis.value}:{case.identifier.variety.value}"
    posterior = None
    if baseline:
        variant = PromptVariant(
            "baseline",
            "baseline",
            case.prompt_text,
            content_sha256=hashlib.sha256(
                case.prompt_text.encode("utf-8")
            ).hexdigest(),
            review_status="dataset",
        )
        number = 0
    else:
        if plan.adaptive_settings.mode is EvaluationMode.ADAPTIVE:
            arm = controller.choose(
                context, tuple(v.arm_id for v in remaining)
            )
            variant = next(v for v in remaining if v.arm_id == arm)
            posterior = controller.posterior(context, arm)
        else:
            variant = remaining[0]
        state["used_variants"] = [*state["used_variants"], variant.variant_id]
        number = len(state["used_variants"])
    return CaseOutcome(
        case,
        variant.variant_id,
        error="Attempt interrupted before verdict commit.",
        variant=variant,
        attempt_number=number,
        posterior_before=posterior,
        submission_uncertain=True,
    )


def _complete(
    outcome: CaseOutcome,
    state: dict[str, Any],
    variants: list[PromptVariant] | tuple[PromptVariant, ...],
    plan: EvaluationPlan,
    controller: ThompsonController,
) -> tuple[CaseOutcome, dict[str, Any]]:
    """Commit known feedback and determine whether the case stops."""
    state = {**state, "pending": None}
    failure = bool(
        outcome.error
        and outcome.error.startswith(("Attempt failed:", "Attempt exceeded"))
    )
    state["technical_failures"] = (
        state.get("technical_failures", 0) + 1 if failure else 0
    )
    if outcome.attempt_number == 0:
        state["baseline_done"] = True
        return outcome, state if variants else _next_case(state, controller)
    context = (
        f"{outcome.case.axis.value}:{outcome.case.identifier.variety.value}"
    )
    if outcome.variant is None:
        raise EvaluationEngineError(
            "Generated attempts require recipe provenance."
        )
    defect = _defect(outcome)
    controller.observe(context, outcome.variant.arm_id, defect)
    exhausted = len(state["used_variants"]) >= len(variants)
    reason = _stop_reason(plan, outcome.attempt_number, defect, exhausted)
    state["controller"] = controller.snapshot()
    if reason:
        return replace(outcome, stop_reason=reason), _next_case(
            state, controller
        )
    return outcome, state


def _stop_reason(
    plan: EvaluationPlan,
    attempt_number: int,
    defect: bool | None,
    exhausted: bool,
) -> str | None:
    """Name why a case stops after this attempt, or None to continue."""
    if plan.adaptive_settings.mode is not EvaluationMode.ADAPTIVE:
        return "enumerated" if exhausted else None
    if defect:
        return "first_defect"
    if attempt_number >= plan.adaptive_settings.attempt_budget:
        return "budget_exhausted"
    return "variants_exhausted" if exhausted else None


async def _initial_state(
    plan: EvaluationPlan,
    target: TargetConnection,
    journal: EvaluationJournal | None,
) -> dict[str, Any]:
    """Resume the journal checkpoint or start at the first case."""
    saved = (
        await asyncio.to_thread(
            journal.initialize, _fingerprint(plan, target), len(plan.cases)
        )
        if journal
        else {}
    )
    return {
        "case_index": 0,
        "baseline_done": False,
        "used_variants": [],
        **saved,
    }


def _next_case(
    state: dict[str, Any], controller: ThompsonController
) -> dict[str, Any]:
    """Advance the checkpoint while retaining controller and failure state."""
    return {
        "case_index": state["case_index"] + 1,
        "baseline_done": False,
        "used_variants": [],
        "pending": None,
        "controller": controller.snapshot(),
        "technical_failures": state.get("technical_failures", 0),
    }


def _fingerprint(plan: EvaluationPlan, target: TargetConnection) -> str:
    """Bind a checkpoint to its evaluation plan and target identity."""
    digest = hashlib.sha256()
    for chunk in json.JSONEncoder(sort_keys=True).iterencode(asdict(plan)):
        digest.update(chunk.encode("utf-8"))
    digest.update(target.base_url.encode("utf-8"))
    digest.update(target.model_name.encode("utf-8"))
    return digest.hexdigest()


def _defect(outcome: CaseOutcome) -> bool | None:
    """Map a complete verdict to the selected axis defect criterion."""
    if not outcome.is_scored:
        return None
    if outcome.case.axis is Axis.ADVERSARIAL:
        return outcome.attack_succeeded
    return (
        None
        if outcome.response_category is ResponseCategory.UNCLEAR
        else outcome.is_refusal
    )
