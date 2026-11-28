"""One OpenAI-compatible gateway for the generator's writing and judging models.

Each role is bound to a route: an endpoint, a model name and its sampling
settings. A reasoning model needs its own token allowance on top of the
answer's, or it spends the whole budget thinking and answers nothing, which
this gateway refuses to return as text. Rate limits and transient server
failures are retried with the wait the server asks for; no provider message,
prompt or key is ever logged.
"""

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx

from harass.application.ports.generation import BriefWriter, WriterTruncatedError

logger = logging.getLogger(__name__)

RETRY_STATUS = frozenset({429, 500, 502, 503})
# The waits span more than a minute so a per-minute quota resets before the
# last attempt gives up.
BACKOFF_SECONDS = (2, 5, 15, 30, 65)
# A reasoning model's thinking is billed against the same token budget.
REASONING_BUDGET = 2048


class ModelGatewayError(RuntimeError):
    """A model could not be reached, or answered nothing usable."""


class ModelTruncatedError(ModelGatewayError):
    """A model spent its whole token budget and wrote no answer."""


@dataclass(frozen=True)
class ModelRoute:
    """Where one role's model lives and how it is sampled."""

    endpoint: str
    api_key: str = field(repr=False)
    model: str
    temperature: float
    max_tokens: int
    reasoning_effort: str | None = None
    extra_body: Mapping[str, Any] = field(default_factory=dict)


class ModelGateway:
    """Sends one prompt at a time to an OpenAI-compatible chat endpoint."""

    def __init__(self, client: httpx.AsyncClient, timeout_seconds: float = 180) -> None:
        """Bind the shared HTTP client and the per-request timeout."""
        self._client = client
        self._timeout_seconds = timeout_seconds

    async def complete(self, route: ModelRoute, prompt: str) -> str:
        """Return the model's answer to one prompt.

        Raises:
            ModelGatewayError: If the endpoint keeps failing, or the model
                answers with reasoning only.
        """
        for pause in (*BACKOFF_SECONDS, None):
            try:
                response = await self._client.post(
                    route.endpoint,
                    json=_body(route, prompt),
                    headers={"Authorization": f"Bearer {route.api_key}"},
                    timeout=self._timeout_seconds,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as error:
                status = error.response.status_code
                if status not in RETRY_STATUS or pause is None:
                    raise ModelGatewayError(
                        f"Model {route.model} failed with HTTP {status}."
                    ) from None
                logger.warning("Model %s returned HTTP %d; retrying.", route.model, status)
                await asyncio.sleep(max(pause, _retry_after(error.response)))
                continue
            except httpx.HTTPError as error:
                raise ModelGatewayError(
                    f"Model {route.model} is unreachable: {type(error).__name__}."
                ) from None
            return _answer(route, response.json())
        raise ModelGatewayError(f"Model {route.model} stayed rate limited.")


class GatewayBriefWriter(BriefWriter):
    """Writes with one model bound to its route."""

    def __init__(self, gateway: ModelGateway, route: ModelRoute) -> None:
        """Bind the gateway and the route of this writing role."""
        self._gateway = gateway
        self._route = route

    async def write(self, brief: str) -> str:
        """Return the model's answer to the brief.

        Raises:
            WriterTruncatedError: If the model ran out of tokens before answering.
        """
        try:
            return await self._gateway.complete(self._route, brief)
        except ModelTruncatedError as error:
            raise WriterTruncatedError(str(error)) from None


class JudgingGateway:
    """Asks a judging model and reads an unobtainable judgment as empty.

    Every caller treats an empty answer as a failed check, so a judgment that
    never arrived can only reject a prompt, never let one through.
    """

    def __init__(self, gateway: ModelGateway) -> None:
        """Bind the shared gateway."""
        self._gateway = gateway

    async def ask(self, route: ModelRoute, prompt: str) -> str:
        """Return the judge's answer, or an empty string when it gave none."""
        try:
            return await self._gateway.complete(route, prompt)
        except ModelGatewayError:
            logger.warning("Judging model %s gave no usable answer.", route.model)
            return ""


def _body(route: ModelRoute, prompt: str) -> dict[str, Any]:
    """Build the chat request, adding a reasoning model's extra allowance."""
    body: dict[str, Any] = {
        "model": route.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": route.temperature,
        "max_tokens": route.max_tokens,
        **route.extra_body,
    }
    if route.reasoning_effort:
        body["reasoning"] = {"effort": route.reasoning_effort}
        body["max_tokens"] = route.max_tokens + REASONING_BUDGET
    return body


def _answer(route: ModelRoute, payload: object) -> str:
    """Read the answer text out of an OpenAI-compatible reply.

    Raises:
        ModelTruncatedError: If the model stopped at its token limit before
            writing anything; a reasoning model can spend it all thinking
            and return no reasoning text either.
        ModelGatewayError: If the reply carries no answer, or carries
            reasoning only, so an empty answer is never scored as text.
    """
    choices = payload.get("choices") if isinstance(payload, dict) else None
    first = choices[0] if isinstance(choices, list) and choices else None
    message = first.get("message") if isinstance(first, dict) else None
    if not isinstance(message, dict):
        raise ModelGatewayError(f"Model {route.model} returned no answer.")
    text = str(message.get("content") or "").strip()
    if not text and first.get("finish_reason") == "length":
        raise ModelTruncatedError(f"Model {route.model} ran out of tokens before answering.")
    if not text and str(message.get("reasoning") or "").strip():
        raise ModelGatewayError(f"Model {route.model} answered with reasoning only.")
    return text


def _retry_after(response: httpx.Response) -> float:
    """Return the wait the server asked for, or zero when it named none."""
    try:
        return float(response.headers.get("retry-after") or 0)
    except ValueError:
        return 0.0
