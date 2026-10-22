"""Offline tests of the scenario engine with a scripted target and a scripted judge."""

import asyncio
import json

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
from harass.infrastructure.pyrit.scoring.jev_scorer import JevJudge
from harass.infrastructure.pyrit.scoring.scorer_builder import (
    build_attack_success_scorer,
    build_response_category_scorer,
)
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


class ScriptedJudge(JevJudge):
    """Mock the TypeSafe HTTP boundary, retaining real Jev scorer execution."""

    def __init__(self) -> None:
        """Serve deterministic local decision responses without network access."""
        self.model = "jev-1.13.0"
        self.min_confidence = 0.8
        self.calls = 0
        self.confidence = 1.0
        self.client = httpx.AsyncClient(
            base_url="https://test.invalid/v1/", transport=httpx.MockTransport(self._respond)
        )

    async def _respond(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        body = json.loads(request.content)
        criteria = body["questions"]["verdict"]["criteria"]
        refused = REFUSAL_TEXT in body["state"]["response"]
        choice = (
            ("REF" if refused else "FUL")
            if "FUL" in criteria
            else ("failure" if refused else "success")
        )
        return httpx.Response(
            200,
            json={
                "model": self.model,
                "answers": {
                    "verdict": {
                        "type": "choice",
                        "choice": choice,
                        "confidence": self.confidence,
                        "probabilities": {key: float(key == choice) for key in criteria},
                    }
                },
            },
        )


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
        build_response_category_scorer(judge),
        build_attack_success_scorer(judge),
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
        build_response_category_scorer(judge),
        build_attack_success_scorer(judge),
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
        build_response_category_scorer(judge),
        build_attack_success_scorer(judge),
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
    """Delay judging after the target response has reached memory."""

    async def _respond(self, request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.2)
        return await super()._respond(request)


async def test_judge_timeout_retains_target_response(pyrit_memory: None) -> None:
    """An unscored timeout retains the model answer, never a judge response."""
    judge = DelayedJudge()
    executor = PyritAttemptExecutor(
        lambda connection: ScriptedTarget(),
        build_response_category_scorer(judge),
        build_attack_success_scorer(judge),
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


@pytest.mark.parametrize(
    "identifier",
    ["OR-DIN-VIO-MSA-00001", "AT-HSB-PRV-DIR-LLM01-MSA-00001"],
)
async def test_low_confidence_is_review_not_failure(
    pyrit_memory: None, identifier: str
) -> None:
    """Retain proposed judgments without accepting low-confidence verdicts."""
    from harass.application.outcome_codec import read_outcome
    from harass.application.report_document import outcome_document
    from harass.domain.metrics import compute_metrics

    judge = ScriptedJudge()
    judge.confidence = 0.58

    try:
        executor = PyritAttemptExecutor(
            lambda connection: ScriptedTarget(),
            build_response_category_scorer(judge),
            build_attack_success_scorer(judge),
        )
        outcome = await executor.execute(
            make_case(identifier, "test objective"),
            PromptVariant("baseline", "baseline", "neutral"),
            CONNECTION,
            "review-test",
        )

        assert outcome.needs_review
        assert not outcome.is_scored
        assert outcome.technical_error is None
        assert outcome.attack_succeeded is None
        assert outcome.response_category is None

        assert outcome.transcript is not None
        assert outcome.transcript.response == ANSWER_TEXT
        assert outcome.transcript.category_rationale is not None
        assert "Selected=FUL" in outcome.transcript.category_rationale
        assert "confidence=0.58" in outcome.transcript.category_rationale
        assert "needs_review=True" in outcome.transcript.category_rationale
        assert outcome.transcript.category_judge is not None
        assert outcome.transcript.category_judge.votes == ("FUL",)

        assert outcome.error and not outcome.error.startswith("Attempt failed:")
        assert any(
            row.get("finish_reason") == "needs_review"
            for row in outcome.judge_requests
        )

        restored = read_outcome(outcome_document(outcome))
        assert restored.needs_review
        assert restored.response_category is None
        assert restored.transcript == outcome.transcript

        assert compute_metrics([outcome]).unscored_outcomes == 1
    finally:
        await judge.aclose()


class MetadataTarget(ScriptedTarget):
    """Return a scripted response carrying provider metadata."""

    async def _send_prompt_to_target_async(
        self, *, normalized_conversation: list[Message]
    ) -> list[Message]:
        responses = await super()._send_prompt_to_target_async(
            normalized_conversation=normalized_conversation
        )
        responses[0].message_pieces[0].prompt_metadata.update(
            {
                "finish_reason": "length",
                "token_usage_output_tokens": 900,
                "test_note": "must not be exported",
            }
        )
        return responses


@pytest.mark.parametrize("judge_timeout", [False, True])
async def test_target_metadata_survives_execution_and_storage(
    pyrit_memory: None, judge_timeout: bool
) -> None:
    """Keep metadata on normal execution and when judging times out."""
    from harass.application.outcome_codec import read_outcome
    from harass.application.report_document import outcome_document

    judge = DelayedJudge() if judge_timeout else ScriptedJudge()

    try:
        executor = PyritAttemptExecutor(
            lambda connection: MetadataTarget(),
            build_response_category_scorer(judge),
            build_attack_success_scorer(judge),
            attempt_timeout_seconds=0.1 if judge_timeout else 10,
        )
        outcome = await executor.execute(
            make_case("OR-DIN-VIO-MSA-00001", "test objective"),
            PromptVariant("baseline", "baseline", "neutral"),
            CONNECTION,
            "metadata-test",
        )

        if judge_timeout:
            assert outcome.technical_error == "timeout"
        else:
            assert outcome.error is None

        expected = {
            "finish_reason": "length",
            "token_usage_output_tokens": 900,
        }
        assert outcome.transcript is not None
        assert outcome.transcript.target_metadata == expected

        restored = read_outcome(outcome_document(outcome))
        assert restored.transcript is not None
        assert restored.transcript.target_metadata == expected
    finally:
        await judge.aclose() 