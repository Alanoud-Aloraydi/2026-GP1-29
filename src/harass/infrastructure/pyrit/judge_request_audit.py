"""Count judge HTTP calls without recording request content."""

from contextvars import ContextVar
from time import perf_counter
from typing import Any

import httpx

JUDGE_REQUESTS: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "judge_requests", default=None
)


def audited_client() -> httpx.AsyncClient:
    """Create an owned HTTP client with public request and response hooks."""
    return httpx.AsyncClient(
        event_hooks={"request": [_request], "response": [_response]}
    )


async def _request(request: httpx.Request) -> None:
    """Record the start of an actual judge request without its payload."""
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
    """Record transport outcome, token usage and completion status."""
    record = response.request.extensions.get("harass_judge_audit")
    if record is None:
        return
    record["http_status"] = response.status_code
    await response.aread()
    record["elapsed_seconds"] = round(perf_counter() - record["_started"], 3)
    try:
        data = response.json()
        choices = data.get("choices") or []
        record["finish_reason"] = (
            choices[0].get("finish_reason") if choices else None
        )
        record["completion_tokens"] = (data.get("usage") or {}).get(
            "completion_tokens"
        )
    except (ValueError, TypeError, AttributeError):
        record["finish_reason"] = "invalid_response"
