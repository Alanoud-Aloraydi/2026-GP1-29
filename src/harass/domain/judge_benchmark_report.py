"""A published judge benchmark report."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class BenchmarkReportRecord:
    """One stored benchmark run with the fields used to list and compare it.

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
