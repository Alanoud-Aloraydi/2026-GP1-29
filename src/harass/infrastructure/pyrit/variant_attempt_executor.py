"""Execute isolated PyRIT attempts with request-aware scoring."""

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import replace
from time import perf_counter

from pyrit.executor.attack import AttackScoringConfig, PromptSendingAttack
from pyrit.executor.attack.core.attack_parameters import AttackParameters
from pyrit.executor.attack.single_turn.single_turn_attack_strategy import (
    SingleTurnAttackContext,
)
from pyrit.memory import CentralMemory
from pyrit.models import Message
from pyrit.prompt_target import PromptTarget
from pyrit.score import Scorer, TrueFalseScorer

from harass.application.ports.attempt_executor import AttemptExecutor
from harass.domain.case_outcome import AttemptTranscript, CaseOutcome
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.owasp_scenario import OwaspScenario, scenario_for
from harass.domain.prompt_variant import PromptVariant
from harass.domain.target_connection import TargetConnection
from harass.domain.taxonomy import Axis
from harass.infrastructure.pyrit.attempt_outcome import read_result
from harass.infrastructure.pyrit.judge_request_audit import JUDGE_REQUESTS
from harass.infrastructure.pyrit.scoring.synthetic_disclosure_scorer import (
    SyntheticDisclosureScorer,
)
from harass.infrastructure.pyrit.target_builder import close_target

logger = logging.getLogger(__name__)


class PyritAttemptExecutor(AttemptExecutor):
    """Execute prepared attempts with isolated target histories."""

    def __init__(
        self,
        target_factory: Callable[[TargetConnection], PromptTarget],
        category_scorer: TrueFalseScorer,
        attack_scorer: TrueFalseScorer,
        attempt_timeout_seconds: float = 300,
    ) -> None:
        """Store the target factory and the shared judge scorers."""
        self._target_factory = target_factory
        self._category_scorer = category_scorer
        self._attack_scorer = attack_scorer
        if attempt_timeout_seconds <= 0:
            raise ValueError("Attempt timeout must be positive.")
        self._attempt_timeout_seconds = attempt_timeout_seconds

    async def execute(
        self,
        case: EvaluationCase,
        variant: PromptVariant,
        target: TargetConnection,
        run_identifier: str,
    ) -> CaseOutcome:
        """Bound target and judge calls without inventing verdicts."""
        requests: list[dict[str, object]] = []
        token = JUDGE_REQUESTS.set(requests)
        started = perf_counter()
        try:
            outcome = await self._execute_attempt(
                case, variant, target, run_identifier
            )
            return replace(
                outcome,
                elapsed_seconds=round(perf_counter() - started, 3),
                judge_requests=tuple(
                    {k: v for k, v in request.items() if not k.startswith("_")}
                    for request in requests
                ),
            )
        finally:
            JUDGE_REQUESTS.reset(token)

    async def _execute_attempt(
        self,
        case: EvaluationCase,
        variant: PromptVariant,
        target: TargetConnection,
        run_identifier: str,
    ) -> CaseOutcome:
        """Execute one isolated request with scenario-appropriate scoring."""
        scenario = scenario_for(case, run_identifier)
        model_attack_judgment = (
            case.axis is Axis.ADVERSARIAL and not scenario.protected_content
        )
        auxiliary: list[Scorer] = (
            [self._category_scorer] if case.axis is Axis.ADVERSARIAL else []
        )
        scorer = (
            self._attack_scorer
            if model_attack_judgment
            else self._category_scorer
        )
        if scenario.protected_content and scenario.protected_marker:
            scorer = SyntheticDisclosureScorer(
                reference=scenario.protected_content,
                marker=scenario.protected_marker,
            )
        objective_target: PromptTarget | None = None
        context = _attack_context(case, variant, scenario, run_identifier)
        try:
            objective_target = self._target_factory(target)
            attack = PromptSendingAttack(
                objective_target=objective_target,
                attack_scoring_config=AttackScoringConfig(
                    objective_scorer=scorer, auxiliary_scorers=auxiliary
                ),
            )
            result = await asyncio.wait_for(
                attack.execute_with_context_async(context=context),
                timeout=self._attempt_timeout_seconds,
            )
            if result.last_response is None:
                return CaseOutcome(
                    case,
                    variant.variant_id,
                    error="The target gave no response.",
                    variant=variant,
                )
            return read_result(case, variant, scenario, result)
        except Exception as error:
            # Do not return provider exception text, which may echo client
            # credentials.
            return CaseOutcome(
                case,
                variant.variant_id,
                error="Attempt exceeded its configured execution timeout."
                if isinstance(error, TimeoutError)
                else f"Attempt failed: {type(error).__name__}.",
                variant=variant,
                scenario_name=scenario.name,
                transcript=_recover_response(
                    context.conversation_id, variant.sent_prompt
                ),
                technical_error=_technical_error(error),
            )
        finally:
            if objective_target is not None:
                await close_target(objective_target)


def _recover_response(
    conversation_id: str, sent_prompt: str
) -> AttemptTranscript | None:
    """Recover a stored target response after a scoring failure."""
    try:
        pieces = CentralMemory.get_memory_instance().get_message_pieces(
            role="assistant", conversation_id=conversation_id
        )
        memory = CentralMemory.get_memory_instance()
        for response in sorted(
            pieces, key=lambda piece: piece.timestamp, reverse=True
        ):
            request = memory.get_request_from_response(
                response=Message(message_pieces=[response])
            )
            if any(
                piece.original_value == sent_prompt
                for piece in request.message_pieces
            ):
                return AttemptTranscript(sent_prompt, response.converted_value)
        return None
    except Exception as error:
        logger.warning(
            "Response evidence unavailable: %s", type(error).__name__
        )
        return None


def _technical_error(error: BaseException) -> str:
    """Classify technical failures without exposing provider details."""
    if isinstance(error, TimeoutError):
        return "timeout"
    seen: set[int] = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        name = type(error).__name__.lower()
        if "json" in name:
            return "invalid_judge_output"
        if "connection" in name or "timeout" in name:
            return "connection"
        cause = error.__cause__ or error.__context__
        if cause is None:
            break
        error = cause
    return "execution"


def _attack_context(
    case: EvaluationCase,
    variant: PromptVariant,
    scenario: OwaspScenario,
    run_identifier: str,
) -> SingleTurnAttackContext[AttackParameters]:
    """Construct isolated target history and stable research correlation."""
    attempt_label = str(uuid.uuid4())
    return SingleTurnAttackContext(
        params=AttackParameters(
            objective=case.objective
            if case.axis is Axis.OVER_REFUSAL
            else (
                f"Criterion: {scenario.criterion}\n"
                f"Original request: {case.objective}"
            ),
            next_message=Message.from_prompt(
                prompt=variant.sent_prompt, role="user"
            ),
            prepended_conversation=[
                Message.from_prompt(
                    prompt=scenario.system_prompt, role="system"
                )
            ]
            if scenario.system_prompt
            else None,
            memory_labels={
                "harass_run": run_identifier,
                "harass_case": str(case.identifier),
                "harass_variant": variant.variant_id,
                "harass_attempt": attempt_label,
            },
        )
    )
