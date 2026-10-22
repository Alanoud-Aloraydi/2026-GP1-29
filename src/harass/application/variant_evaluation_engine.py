"""Feedback-driven evaluation with bounded recipe memory and durable attempt reservations."""

import asyncio
import hashlib
import json
from dataclasses import asdict, replace
from typing import Any

from harass.application.errors import EvaluationEngineError
from harass.application.outcome_codec import read_outcome
from harass.application.ports.attempt_executor import AttemptExecutor
from harass.application.ports.evaluation_engine import EvaluationEngine
from harass.application.ports.evaluation_journal import EvaluationJournal
from harass.application.ports.run_queue import EvaluationSuspendedError, EvaluationYieldedError
from harass.application.ports.variant_catalog import VariantCatalog
from harass.application.report_document import outcome_document
from harass.domain.adaptive_controller import ThompsonController
from harass.domain.case_outcome import CaseOutcome
from harass.domain.evaluation_plan import EvaluationPlan
from harass.domain.prompt_variant import EvaluationMode, PromptVariant, VariantSelection
from harass.domain.target_connection import TargetConnection
from harass.domain.taxonomy import Axis, ResponseCategory


class VariantEvaluationEngine(EvaluationEngine):
    """Preserve serial adaptive feedback while checkpointing each submitted attempt."""

    def __init__(
        self, catalog: VariantCatalog, executor: AttemptExecutor, *, quantum_attempts: int = 50
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
        """Generate the current case's recipes and recover uncertain attempts as unscored."""
        selection = plan.variant_selection or VariantSelection((), ())
        if not plan.include_baseline:
            for case in plan.cases:
                if not self._catalog.variants(case, selection):
                    raise EvaluationEngineError(
                        "A selected case has no eligible variants or baseline."
                    )
        state = (
            await asyncio.to_thread(
                journal.initialize, _fingerprint(plan, target), len(plan.cases)
            )
            if journal
            else {}
        )
        state = {"case_index": 0, "baseline_done": False, "used_variants": [], **state}
        controller = ThompsonController(plan.adaptive_settings.random_seed)
        if state.get("controller"):
            controller.restore(state["controller"])
        outcomes: list[CaseOutcome] = []
        committed = 0
        while state["case_index"] < len(plan.cases):
            case = plan.cases[state["case_index"]]
            variants = self._catalog.variants(case, selection)
            if state.get("pending"):
                outcome = read_outcome(state["pending"])
                outcome, state = _complete(outcome, state, variants, plan, controller)
                if journal:
                    await asyncio.to_thread(journal.commit, outcome, state)
                else:
                    outcomes.append(outcome)
                continue
            remaining = [v for v in variants if v.variant_id not in state["used_variants"]]
            baseline = plan.include_baseline and not state["baseline_done"]
            if not baseline and not remaining:
                state = _next_case(state, controller)
                if journal:
                    await asyncio.to_thread(journal.reserve, state)
                continue
            context = f"{case.axis.value}:{case.identifier.variety.value}"
            posterior = None
            if baseline:
                variant = PromptVariant(
                    "baseline",
                    "baseline",
                    case.prompt_text,
                    content_sha256=hashlib.sha256(case.prompt_text.encode("utf-8")).hexdigest(),
                    review_status="dataset",
                )
                number = 0
            else:
                if plan.adaptive_settings.mode is EvaluationMode.ADAPTIVE:
                    arm = controller.choose(context, tuple(v.arm_id for v in remaining))
                    variant = next(v for v in remaining if v.arm_id == arm)
                    posterior = controller.posterior(context, arm)
                else:
                    variant = remaining[0]
                state["used_variants"] = [*state["used_variants"], variant.variant_id]
                number = len(state["used_variants"])
            reservation = CaseOutcome(
                case,
                variant.variant_id,
                error="Attempt interrupted before verdict commit.",
                variant=variant,
                attempt_number=number,
                posterior_before=posterior,
                submission_uncertain=True,
            )
            state = {
                **state,
                "controller": controller.snapshot(),
                "pending": outcome_document(reservation),
            }
            if journal:
                await asyncio.to_thread(journal.reserve, state)
            outcome = await self._executor.execute(case, variant, target, run_identifier)
            outcome = replace(
                outcome, variant=variant, attempt_number=number, posterior_before=posterior
            )
            outcome, state = _complete(outcome, state, variants, plan, controller)
            if journal:
                await asyncio.to_thread(journal.commit, outcome, state)
                committed += 1
                if state.get("technical_failures", 0) >= 3:
                    raise EvaluationSuspendedError(
                        "Target or judge repeatedly unavailable; saved progress can be resumed."
                    )
                if committed >= self._quantum_attempts and state["case_index"] < len(plan.cases):
                    raise EvaluationYieldedError("Committed work yielded the judge slot.")
            else:
                outcomes.append(outcome)
        return (
            await asyncio.to_thread(lambda: list(journal.outcomes(lightweight=True)))
            if journal
            else outcomes
        )


def _complete(
    outcome: CaseOutcome,
    state: dict[str, Any],
    variants: list[PromptVariant] | tuple[PromptVariant, ...],
    plan: EvaluationPlan,
    controller: ThompsonController,
) -> tuple[CaseOutcome, dict[str, Any]]:
    state = {**state, "pending": None}
    failure = bool(
        outcome.error and outcome.error.startswith(("Attempt failed:", "Attempt exceeded"))
    )
    state["technical_failures"] = state.get("technical_failures", 0) + 1 if failure else 0
    if outcome.attempt_number == 0:
        state["baseline_done"] = True
        return outcome, state if variants else _next_case(state, controller)
    context = f"{outcome.case.axis.value}:{outcome.case.identifier.variety.value}"
    if outcome.variant is None:
        raise EvaluationEngineError("Generated attempts require recipe provenance.")
    defect = _defect(outcome)
    controller.observe(context, outcome.variant.arm_id, defect)
    adaptive = plan.adaptive_settings.mode is EvaluationMode.ADAPTIVE
    budget = plan.adaptive_settings.attempt_budget if adaptive else len(variants)
    exhausted = len(state["used_variants"]) >= len(variants)
    reason = (
        "first_defect"
        if adaptive and defect
        else "budget_exhausted"
        if adaptive and outcome.attempt_number >= budget
        else "variants_exhausted"
        if adaptive and exhausted
        else "enumerated"
        if exhausted
        else None
    )
    state["controller"] = controller.snapshot()
    if reason:
        return replace(outcome, stop_reason=reason), _next_case(state, controller)
    return outcome, state


def _next_case(state: dict[str, Any], controller: ThompsonController) -> dict[str, Any]:
    return {
        "case_index": state["case_index"] + 1,
        "baseline_done": False,
        "used_variants": [],
        "pending": None,
        "controller": controller.snapshot(),
        "technical_failures": state.get("technical_failures", 0),
    }


def _fingerprint(plan: EvaluationPlan, target: TargetConnection) -> str:
    digest = hashlib.sha256()
    for chunk in json.JSONEncoder(sort_keys=True).iterencode(asdict(plan)):
        digest.update(chunk.encode("utf-8"))
    digest.update(target.base_url.encode("utf-8"))
    digest.update(target.model_name.encode("utf-8"))
    return digest.hexdigest()

def _defect(outcome: CaseOutcome) -> bool | None:
    if outcome.case.axis is Axis.ADVERSARIAL:
        return outcome.attack_succeeded if outcome.is_attack_scored else None

    if not outcome.is_category_scored:
        return None

    return None if outcome.response_category is ResponseCategory.UNCLEAR else outcome.is_refusal