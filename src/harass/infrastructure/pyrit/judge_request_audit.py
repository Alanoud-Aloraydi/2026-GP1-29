"""Per-attempt decision request audit; credentials and prompt text are excluded."""

from contextvars import ContextVar
from typing import Any

JUDGE_REQUESTS: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "judge_requests", default=None
)
