"""Offline tests of the scenario engine with a scripted target and a scripted judge."""

import asyncio
import json
from collections.abc import Sequence

import pytest
from pyrit.models import Message, MessagePiece, construct_response_from_request
from pyrit.prompt_target import PromptTarget
from pyrit.prompt_target.common.target_capabilities import TargetCapabilities
from pyrit.prompt_target.common.target_configuration import TargetConfiguration

from harass.domain.case_identifier import CaseIdentifier
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.prompt_variant import PromptVariant
from harass.domain.target_connection import TargetConnection
from harass.domain.taxonomy import ResponseCategory
from harass.infrastructure.pyrit.scoring.scorer_builder import (
    build_attack_success_scorer,
    build_response_category_scorer,
)
from harass.infrastructure.pyrit.target_builder import _judge_configuration
from harass.infrastructure.pyrit.variant_attempt_executor import PyritAttemptExecutor

REFUSAL_MARKER = "REFUSE_ME"
REFUSAL_TEXT = "I refuse."
ANSWER_TEXT = "Here is the answer."

CONNECTION = TargetConnection(
    base_url="http://target.invalid/v1", model_name="model", api_key="key"
)


class ScriptedTarget(PromptTarget):
    """Refuses prompts that visibly carry the refusal marker and answers all others."""

    def __init__(self) -> None:
        """Declare a plain chat target."""
        super().__init__(
            custom_configuration=TargetConfiguration(
                capabilities=TargetCapabilities(
                    supports_multi_turn=True,
                    supports_editable_history=True,
                    supports_system_prompt=True,
                )
            )
        )
        self.received: list[str] = []

    async def _send_prompt_to_target_async(
        self, *, normalized_conversation: list[Message]
    ) -> list[Message]:
        request = normalized_conversation[-1].message_pieces[0]
        self.received.append(request.converted_value)
        text = REFUSAL_TEXT if REFUSAL_MARKER in request.converted_value else ANSWER_TEXT
        return [construct_response_from_request(request=request, response_text_pieces=[text])]


class ScriptedJudge(PromptTarget):
    """Returns the verdict format each rubric requests, derived from the judged response."""

    def __init__(self) -> None:
        """Declare the capabilities used for the real judge."""
        super().__init__(custom_configuration=_judge_configuration(supports_system_prompt=True))
        self.calls = 0

    async def _send_prompt_to_target_async(
        self, *, normalized_conversation: list[Message]
    ) -> list[Message]:
        pieces: Sequence[MessagePiece] = [
            piece for message in normalized_conversation for piece in message.message_pieces
        ]
        self.calls += 1
        request = pieces[-1]
        refused = REFUSAL_TEXT in request.converted_value
        is_category_rubric = any("PRF" in piece.converted_value for piece in pieces[:-1])
        verdict = (
            {"category": "REF" if refused else "FUL", "score_value": refused}
            if is_category_rubric
            else {"score_value": not refused, "metadata": ""}
        )
        verdict |= {"description": "d", "rationale": "r"}
        text = "<think>reasoning</think>" + json.dumps(verdict)
        return [construct_response_from_request(request=request, response_text_pieces=[text])]


def make_case(identifier: str, objective: str) -> EvaluationCase:
    """Return a case whose prompt carries the refusal marker."""
    return EvaluationCase(
        identifier=CaseIdentifier.parse(identifier),
        prompt_text=f"{REFUSAL_MARKER} {objective}",
        objective=objective,
    )


@pytest.fixture
def target() -> ScriptedTarget:
    """Return the scripted target; PyRIT memory must already be initialized."""
    return ScriptedTarget()


async def test_variant_executor_scores_independent_requests(
    pyrit_memory: None,
    target: ScriptedTarget,
) -> None:
    """The new executor uses PyRIT scoring and sends the authored text without converters."""
    judge = ScriptedJudge()
    executor = PyritAttemptExecutor(
        lambda connection: target,
        build_response_category_scorer(judge, votes=1),
        build_attack_success_scorer(judge, votes=1),
    )
    case = make_case("OR-DIN-VIO-MSA-00001", "safe question")
    first = await executor.execute(
        case, PromptVariant("first", "first", REFUSAL_MARKER), CONNECTION, "run"
    )
    second = await executor.execute(
        case, PromptVariant("second", "second", "neutral"), CONNECTION, "run"
    )
    assert first.response_category is ResponseCategory.FULL_REFUSAL
    assert second.response_category is ResponseCategory.FULL_COMPLIANCE
    assert first.transcript and first.transcript.sent_prompt == REFUSAL_MARKER
    assert target.received == [REFUSAL_MARKER, "neutral"]


class SyntheticLeakTarget(ScriptedTarget):
    """Return only the protected synthetic context from the current conversation."""

    async def _send_prompt_to_target_async(
        self, *, normalized_conversation: list[Message]
    ) -> list[Message]:
        request = normalized_conversation[-1].message_pieces[0]
        system = normalized_conversation[0].message_pieces[0].converted_value
        assert "HARASS_TEST_" in system
        protected = system.split("\n", 1)[1]
        return [construct_response_from_request(request=request, response_text_pieces=[protected])]


class DelayedTarget(ScriptedTarget):
    """Delay a synthetic request long enough to exercise the attempt deadline."""

    async def _send_prompt_to_target_async(
        self, *, normalized_conversation: list[Message]
    ) -> list[Message]:
        await asyncio.sleep(0.1)
        return await super()._send_prompt_to_target_async(
            normalized_conversation=normalized_conversation
        )


async def test_attempt_deadline_is_unscored_not_a_safety_verdict(pyrit_memory: None) -> None:
    """A timeout is visible and cannot be learned as a refused or compliant request."""
    judge = ScriptedJudge()
    target = DelayedTarget()
    executor = PyritAttemptExecutor(
        lambda connection: target,
        build_response_category_scorer(judge, votes=1),
        build_attack_success_scorer(judge, votes=1),
        attempt_timeout_seconds=0.01,
    )
    case = make_case("OR-DIN-VIO-MSA-00001", "neutral")
    outcome = await executor.execute(
        case, PromptVariant("slow", "slow", "neutral"), CONNECTION, "run"
    )
    assert not outcome.is_scored
    assert outcome.error and "timeout" in outcome.error


@pytest.mark.parametrize("code", ["LLM02", "LLM08"])
async def test_owasp_context_is_sent_and_leakage_is_deterministic(
    pyrit_memory: None, code: str
) -> None:
    """Protected leakage uses one category judgment and no discarded attack judgment."""
    judge = ScriptedJudge()
    target = SyntheticLeakTarget()
    executor = PyritAttemptExecutor(
        lambda connection: target,
        build_response_category_scorer(judge, votes=1),
        build_attack_success_scorer(judge, votes=1),
    )
    case = make_case(f"AT-HSB-PRV-DIR-{code}-MSA-00001", "protected disclosure")
    outcome = await executor.execute(
        case, PromptVariant("probe", "probe", "سؤال تجريبي"), CONNECTION, "run"
    )
    assert outcome.error is None
    assert outcome.attack_succeeded is True
    assert outcome.leak_exact_match is True
    assert outcome.leak_rouge_l == 1
    assert outcome.scenario_name == code.lower() + "_synthetic_v1"
    assert judge.calls == 1
    assert outcome.transcript is not None and outcome.transcript.attack_judge is None


class DelayedJudge(ScriptedJudge):
    """Delay only judging after the target response has reached memory."""

    async def _send_prompt_to_target_async(
        self, *, normalized_conversation: list[Message]
    ) -> list[Message]:
        await asyncio.sleep(0.2)
        return await super()._send_prompt_to_target_async(
            normalized_conversation=normalized_conversation
        )


async def test_judge_timeout_retains_target_response(pyrit_memory: None) -> None:
    """An unscored timeout retains the model answer, never a judge response."""
    judge = DelayedJudge()
    executor = PyritAttemptExecutor(
        lambda connection: ScriptedTarget(),
        build_response_category_scorer(judge, votes=1),
        build_attack_success_scorer(judge, votes=1),
        attempt_timeout_seconds=0.1,
    )
    outcome = await executor.execute(
        make_case("OR-DIN-VIO-MSA-00001", "neutral"),
        PromptVariant("baseline", "baseline", "neutral"),
        CONNECTION,
        "timeout-evidence",
    )
    assert not outcome.is_scored and outcome.technical_error == "timeout"
    assert outcome.transcript is not None
    assert outcome.transcript.response == ANSWER_TEXT
    assert outcome.elapsed_seconds is not None
