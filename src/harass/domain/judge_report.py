"""Published benchmark reports of response judges."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class JudgeReportRecord:
    """One judge measured against the gold labels, with its full metrics.

    The document holds metrics only; it never contains prompts or responses.
    """

    report_id: str
    created_at: datetime
    judge_model: str
    quantization: str | None
    split: str
    trials: int
    cases: int
    rubric_fingerprint: str
    document: dict[str, Any]
