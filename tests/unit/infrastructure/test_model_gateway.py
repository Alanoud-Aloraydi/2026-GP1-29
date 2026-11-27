"""Tests for the generator's model gateway and its judging wrapper."""

import asyncio
import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import httpx
import pytest

from harass.infrastructure.http.model_gateway import (
    REASONING_BUDGET,
    GatewayBriefWriter,
    JudgingGateway,
    ModelGateway,
    ModelGatewayError,
    ModelRoute,
)

ROUTE = ModelRoute(
    endpoint="https://models.invalid/v1/chat/completions",
    api_key="generator-key",
    model="writer-model",
    temperature=0.7,
    max_tokens=400,
)
type Handler = Callable[[httpx.Request], httpx.Response]


def answered(content: str, reasoning: str | None = None) -> dict[str, Any]:
    """Return an OpenAI-compatible reply body."""
    return {"choices": [{"message": {"content": content, "reasoning": reasoning}}]}


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


def test_the_route_keeps_its_key_out_of_its_representation() -> None:
    """Verify a logged route cannot leak the generator's key."""
    assert "generator-key" not in repr(ROUTE)
