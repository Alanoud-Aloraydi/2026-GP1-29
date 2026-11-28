"""Tests for the generator's model gateway and its judging wrapper."""

import asyncio
import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import httpx
import pytest

from harass.application.ports.generation import WriterTruncatedError
from harass.bootstrap.generation import _attack, _writer
from harass.domain.generation.cells import plan_attack_round
from harass.domain.generation.novelty import KnownPrompts
from harass.domain.taxonomy import ArabicVariety
from harass.infrastructure.http.model_gateway import (
    REASONING_BUDGET,
    GatewayBriefWriter,
    JudgingGateway,
    ModelGateway,
    ModelGatewayError,
    ModelRoute,
    ModelTruncatedError,
)
from harass.infrastructure.settings import GenerationModel, GenerationSettings

ROUTE = ModelRoute(
    endpoint="https://models.invalid/v1/chat/completions",
    api_key="generator-key",
    model="writer-model",
    temperature=0.7,
    max_tokens=400,
)
type Handler = Callable[[httpx.Request], httpx.Response]


def answered(
    content: str, reasoning: str | None = None, finish_reason: str = "stop"
) -> dict[str, Any]:
    """Return an OpenAI-compatible reply body."""
    message = {"content": content, "reasoning": reasoning}
    return {"choices": [{"message": message, "finish_reason": finish_reason}]}


def truncated(request: httpx.Request) -> httpx.Response:
    """Answer as a reasoning model that thought until its token limit."""
    return httpx.Response(200, json=answered("", finish_reason="length"))


def gateway(handler: Handler) -> tuple[ModelGateway, httpx.AsyncClient]:
    """Return a gateway over a scripted transport and its client."""
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ModelGateway(client), client


@pytest.fixture(autouse=True)
def _instant_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the retry waits out of the test run."""

    async def no_wait(seconds: float) -> None:
        """Return at once instead of waiting."""

    monkeypatch.setattr(asyncio, "sleep", no_wait)


async def test_a_reasoning_model_gets_its_own_token_allowance() -> None:
    """Verify thinking tokens are added on top of the answer's budget."""
    bodies: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Record the body and answer it."""
        bodies.append(request.content)
        return httpx.Response(200, json=answered("SAFE"))

    model_gateway, client = gateway(handler)
    async with client:
        await model_gateway.complete(replace(ROUTE, reasoning_effort="low"), "rubric")
    body = json.loads(bodies[0])
    assert body["max_tokens"] == ROUTE.max_tokens + REASONING_BUDGET
    assert body["reasoning"] == {"effort": "low"}


async def test_a_rate_limit_is_retried_and_then_succeeds() -> None:
    """Verify a 429 waits and the next attempt's answer is returned."""
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Refuse once with a rate limit, then answer."""
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(429, headers={"retry-after": "0"}, json={})
        return httpx.Response(200, json=answered("answer"))

    model_gateway, client = gateway(handler)
    async with client:
        assert await model_gateway.complete(ROUTE, "brief") == "answer"
    assert len(attempts) == 2


async def test_a_rejected_request_reports_only_its_status() -> None:
    """Verify a provider's own message never reaches the error."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Refuse with a message that must not be exposed."""
        return httpx.Response(400, json={"error": {"message": "invalid api key sk-secret"}})

    model_gateway, client = gateway(handler)
    async with client:
        with pytest.raises(ModelGatewayError) as failure:
            await model_gateway.complete(ROUTE, "brief")
    assert "HTTP 400" in str(failure.value)
    assert "sk-secret" not in str(failure.value)


async def test_an_answer_of_reasoning_only_is_refused() -> None:
    """Verify a model that only thinks is never read as an answer."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Answer with reasoning and no content."""
        return httpx.Response(200, json=answered("", reasoning="thinking at length"))

    model_gateway, client = gateway(handler)
    async with client:
        with pytest.raises(ModelGatewayError, match="reasoning only"):
            await model_gateway.complete(ROUTE, "brief")


async def test_a_reply_without_choices_is_refused() -> None:
    """Verify a malformed reply raises instead of becoming empty text."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Answer with no choices at all."""
        return httpx.Response(200, json={"id": "1"})

    model_gateway, client = gateway(handler)
    async with client:
        with pytest.raises(ModelGatewayError, match="no answer"):
            await model_gateway.complete(ROUTE, "brief")


async def test_a_judge_that_cannot_answer_returns_nothing() -> None:
    """Verify judging fails closed: an unreachable judge gives empty text."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Fail with a server error on every attempt."""
        return httpx.Response(503, json={})

    model_gateway, client = gateway(handler)
    async with client:
        assert await JudgingGateway(model_gateway).ask(ROUTE, "rubric") == ""


async def test_the_gateway_leaves_a_working_answer_untouched() -> None:
    """Verify judging passes the model's own text through."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Answer with a verdict."""
        return httpx.Response(200, json=answered("  VERDICT: SAFE  "))

    model_gateway, client = gateway(handler)
    async with client:
        assert await JudgingGateway(model_gateway).ask(ROUTE, "rubric") == "VERDICT: SAFE"


async def test_requests_carry_the_route_body() -> None:
    """Verify the endpoint, key, model name and sampling of the route are sent."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Record the request and answer it."""
        seen.append(request)
        return httpx.Response(200, json=answered("النص المكتوب"))

    model_gateway, client = gateway(handler)
    async with client:
        assert await GatewayBriefWriter(model_gateway, ROUTE).write("brief") == "النص المكتوب"
    assert str(seen[0].url) == ROUTE.endpoint
    assert seen[0].headers["authorization"] == "Bearer generator-key"
    body = json.loads(seen[0].content)
    assert body["model"] == "writer-model"
    assert body["temperature"] == ROUTE.temperature
    assert body["max_tokens"] == ROUTE.max_tokens
    assert body["messages"] == [{"role": "user", "content": "brief"}]
    assert "reasoning" not in body


async def test_an_empty_answer_cut_at_the_token_limit_is_its_own_failure() -> None:
    """Verify a truncated answer is told apart from an empty or reasoning-only one."""
    model_gateway, client = gateway(truncated)
    async with client:
        with pytest.raises(ModelTruncatedError, match="ran out of tokens"):
            await model_gateway.complete(ROUTE, "brief")


async def test_a_truncated_writer_raises_the_port_error() -> None:
    """Verify the writer reports truncation through the application port."""
    model_gateway, client = gateway(truncated)
    async with client:
        with pytest.raises(WriterTruncatedError):
            await GatewayBriefWriter(model_gateway, ROUTE).write("brief")


async def test_a_truncated_judge_still_fails_closed() -> None:
    """Verify judging is unchanged: a truncated judgment reads as empty."""
    model_gateway, client = gateway(truncated)
    async with client:
        assert await JudgingGateway(model_gateway).ask(ROUTE, "rubric") == ""


async def test_a_cut_off_answer_with_text_is_kept() -> None:
    """Verify text written before the token limit is still returned."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Answer with partial text stopped at the limit."""
        return httpx.Response(200, json=answered("نص ناقص", finish_reason="length"))

    model_gateway, client = gateway(handler)
    async with client:
        assert await model_gateway.complete(ROUTE, "brief") == "نص ناقص"


async def test_only_the_attacker_routes_disable_thinking() -> None:
    """Verify the attack writer asks Venice to skip thinking; judges and writers do not."""
    bodies: dict[str, list[dict[str, Any]]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        """Record each body by model and answer the attacker with a usable attack."""
        body = json.loads(request.content)
        bodies.setdefault(body["model"], []).append(body)
        content = '{"prompt": "نص", "harmful_goal": "هدف", "false_claim": "ادعاء"}'
        return httpx.Response(200, json=answered(content if body["model"] == "attacker" else ""))

    def model(name: str) -> GenerationModel:
        """Return a generator model on the fake endpoint."""
        return GenerationModel(ROUTE.endpoint, "generator-key", name)

    settings = GenerationSettings(
        model("writer"), model("writer"), model("reviewer"), model("judge"), model("attacker")
    )
    model_gateway, client = gateway(handler)
    cell = plan_attack_round(1, [], varieties=frozenset({ArabicVariety.MODERN_STANDARD}))[0]
    async with client:
        pipeline = _attack(model_gateway, JudgingGateway(model_gateway), settings)
        assert pipeline is not None
        await pipeline.produce(cell, None, [], KnownPrompts.of([]))
        await _writer(model_gateway, settings.writer, 0.7, 400).write("brief")
    skip_thinking = {"disable_thinking": True}
    assert all(body["venice_parameters"] == skip_thinking for body in bodies["attacker"])
    assert all("venice_parameters" not in body for body in bodies["reviewer"] + bodies["writer"])


def test_the_route_keeps_its_key_out_of_its_representation() -> None:
    """Verify a logged route cannot leak the generator's key."""
    assert "generator-key" not in repr(ROUTE)
