"""Count actual judge HTTP requests without recording headers or prompt content."""

from contextvars import ContextVar
from time import perf_counter
from typing import Any

import httpx
from pyrit.prompt_target import OpenAIChatTarget

JUDGE_REQUESTS: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "judge_requests", default=None
)


def attach_request_audit(target: OpenAIChatTarget) -> None:
    """Attach HTTPX hooks through the pinned PyRIT SDK-client adapter."""
    target._client._client.event_hooks["request"].append(_request)
    target._client._client.event_hooks["response"].append(_response)


async def _request(request: httpx.Request) -> None:
    records = JUDGE_REQUESTS.get()
    if records is not None:
        record: dict[str, Any] = {
            "http_status": None,
            "elapsed_seconds": None,
            "finish_reason": None,
            "completion_tokens": None,
            "_started": perf_counter(),
        }
        records.append(record)
        request.extensions["harass_judge_audit"] = record


async def _response(response: httpx.Response) -> None:
    record = response.request.extensions.get("harass_judge_audit")
    if record is None:
        return
    record["http_status"] = response.status_code
    await response.aread()
    record["elapsed_seconds"] = round(perf_counter() - record["_started"], 3)
    try:
        data = response.json()
        choices = data.get("choices") or []
        record["finish_reason"] = choices[0].get("finish_reason") if choices else None
        record["completion_tokens"] = (data.get("usage") or {}).get("completion_tokens")
    except (ValueError, TypeError, AttributeError):
        record["finish_reason"] = "invalid_response"
