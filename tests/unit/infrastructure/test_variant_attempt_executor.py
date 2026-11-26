"""Tests for variant attempt executor."""

import asyncio
import json
from typing import Any

import httpx
import pytest
from pyrit.models import Message, construct_response_from_request
from pyrit.prompt_target import PromptTarget
from pyrit.prompt_target.common.target_capabilities import TargetCapabilities
from pyrit.prompt_target.common.target_configuration import TargetConfiguration

from harass.domain.case_identifier import CaseIdentifier
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.prompt_variant import PromptVariant
from harass.domain.target_connection import TargetConnection
from harass.domain.taxonomy import ResponseCategory
from harass.infrastructure.pyrit.scoring.guard_scorers import (
    GuardAttackScorer,
    GuardCategoryScorer,
    GuardModerator,
)
from harass.infrastructure.pyrit.variant_attempt_executor import PyritAttemptExecutor

REFUSAL_MARKER = "REFUSE_ME"
REFUSAL_TEXT = "I refuse."
ANSWER_TEXT = "Here is the answer."

CONNECTION = TargetConnection(
    base_url="http://target.invalid/v1", model_name="model", api_key="key"
)


class ScriptedTarget(PromptTarget):
    """Test double for scripted target."""

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


class Guard:
    """A scripted judge server that refuses when the response says so."""

    def __init__(self, delay: float = 0.0, safety: str | None = None, status: int = 200) -> None:
        """Record every moderation request it receives."""
        self.requests: list[dict[str, Any]] = []
        self._delay = delay
        self._safety = safety
        self._status = status

    async def handle(self, request: httpx.Request) -> httpx.Response:
        """Answer a moderation request in the format the server returns."""
        body = json.loads(request.content)
        self.requests.append(body)
        await asyncio.sleep(self._delay)
        if self._status != 200:
            return httpx.Response(self._status)
        refused = REFUSAL_TEXT in body["messages"][-1]["content"]
        safety = self._safety or ("Safe" if refused else "Unsafe")
        text = f"Safety: {safety}\nCategories: None\nRefusal: {'Yes' if refused else 'No'}"
        return httpx.Response(200, json={"text": text})

    def scorers(self) -> tuple[GuardCategoryScorer, GuardAttackScorer]:
        """Build the production scorers on top of this scripted server."""
        client = httpx.AsyncClient(
            base_url="http://judge.test", transport=httpx.MockTransport(self.handle)
        )
        moderator = GuardModerator(client)
        return (GuardCategoryScorer(moderator=moderator), GuardAttackScorer(moderator=moderator))


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
    pyrit_memory: None, target: ScriptedTarget
) -> None:
    """Verify variant executor scores independent requests."""
    guard = Guard()
    executor = PyritAttemptExecutor(lambda connection: target, *guard.scorers())
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
    assert [request["messages"][0]["content"] for request in guard.requests] == [
        REFUSAL_MARKER,
        "neutral",
    ]


async def test_the_guard_judges_both_axes_with_one_request(
    pyrit_memory: None, target: ScriptedTarget
) -> None:
    """The attack and category scorers share one moderation of a response."""
    guard = Guard()
    executor = PyritAttemptExecutor(lambda connection: target, *guard.scorers())

    outcome = await executor.execute(
        make_case("AT-HSB-PRV-DIR-LLM01-MSA-00001", "attack"),
        PromptVariant("probe", "probe", "neutral"),
        CONNECTION,
        "run",
    )

    assert outcome.error is None
    assert outcome.attack_succeeded is True
    assert outcome.response_category is ResponseCategory.FULL_COMPLIANCE
    assert len(guard.requests) == 1
    assert outcome.transcript is not None
    assert outcome.transcript.attack_judge is not None
    assert outcome.transcript.attack_judge.vote_budget == 1


class SyntheticLeakTarget(ScriptedTarget):
    """Test double for synthetic leak target."""

    async def _send_prompt_to_target_async(
        self, *, normalized_conversation: list[Message]
    ) -> list[Message]:
        request = normalized_conversation[-1].message_pieces[0]
        system = normalized_conversation[0].message_pieces[0].converted_value
        assert "HARASS_TEST_" in system
        protected = system.split("\n", 1)[1]
        return [construct_response_from_request(request=request, response_text_pieces=[protected])]


class DelayedTarget(ScriptedTarget):
    """Test double for delayed target."""

    async def _send_prompt_to_target_async(
        self, *, normalized_conversation: list[Message]
    ) -> list[Message]:
        await asyncio.sleep(0.1)
        return await super()._send_prompt_to_target_async(
            normalized_conversation=normalized_conversation
        )


async def test_attempt_deadline_is_unscored_not_a_safety_verdict(pyrit_memory: None) -> None:
    """Verify attempt deadline is unscored not safety verdict."""
    target = DelayedTarget()
    executor = PyritAttemptExecutor(
        lambda connection: target, *Guard().scorers(), attempt_timeout_seconds=0.01
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
    """Verify owasp context is sent and leakage is deterministic."""
    guard = Guard()
    target = SyntheticLeakTarget()
    executor = PyritAttemptExecutor(lambda connection: target, *guard.scorers())
    case = make_case(f"AT-HSB-PRV-DIR-{code}-MSA-00001", "protected disclosure")
    outcome = await executor.execute(
        case, PromptVariant("probe", "probe", "سؤال تجريبي"), CONNECTION, "run"
    )
    assert outcome.error is None
    assert outcome.attack_succeeded is True
    assert outcome.leak_exact_match is True
    assert outcome.leak_rouge_l == 1
    assert outcome.scenario_name == code.lower() + "_synthetic_v1"
    assert len(guard.requests) == 1
    assert outcome.transcript is not None and outcome.transcript.attack_judge is None


async def test_judge_timeout_retains_target_response(pyrit_memory: None) -> None:
    """An unscored timeout retains the model answer, never a judge response."""
    executor = PyritAttemptExecutor(
        lambda connection: ScriptedTarget(),
        *Guard(delay=0.2).scorers(),
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


async def test_a_controversial_response_leaves_the_attack_unscored(
    pyrit_memory: None, target: ScriptedTarget
) -> None:
    """An abstention is reported, never counted as a failed attack."""
    executor = PyritAttemptExecutor(
        lambda connection: target, *Guard(safety="Controversial").scorers()
    )

    outcome = await executor.execute(
        make_case("AT-HSB-PRV-DIR-LLM01-MSA-00001", "attack"),
        PromptVariant("probe", "probe", "neutral"),
        CONNECTION,
        "run",
    )

    assert outcome.attack_succeeded is None
    assert outcome.error and "abstained" in outcome.error
    assert not outcome.is_scored


async def test_an_unavailable_judge_never_becomes_a_verdict(
    pyrit_memory: None, target: ScriptedTarget
) -> None:
    """A failing judge server leaves the attempt unscored with its evidence."""
    executor = PyritAttemptExecutor(lambda connection: target, *Guard(status=503).scorers())

    outcome = await executor.execute(
        make_case("OR-DIN-VIO-MSA-00001", "neutral"),
        PromptVariant("baseline", "baseline", "neutral"),
        CONNECTION,
        "run",
    )

    assert not outcome.is_scored
    assert outcome.response_category is None
    assert outcome.transcript is not None
    assert outcome.transcript.response == ANSWER_TEXT
