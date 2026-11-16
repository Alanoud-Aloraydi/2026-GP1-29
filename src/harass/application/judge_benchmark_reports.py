"""Publish judge benchmark reports and read them for administrators."""

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from harass.application.errors import (
    InvalidBenchmarkReportError,
    UnknownBenchmarkReportError,
)
from harass.application.ports.judge_benchmark_store import JudgeBenchmarkStore
from harass.domain.judge_benchmark_report import BenchmarkReportRecord

SPLITS = frozenset({"dev", "test", "all"})
LIST_LIMIT = 100


class JudgeBenchmarkReports:
    """Validate, store and summarize benchmark reports."""

    def __init__(
        self,
        store: JudgeBenchmarkStore,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Bind the store and the clock used for the publication time."""
        self._store = store
        self._clock = clock

    def publish(self, document: Mapping[str, Any]) -> str:
        """Store a report once; publishing the same content returns its id."""
        record = _record(str(uuid4()), self._clock(), document)
        return self._store.add(record, _content_hash(document))

    def summaries(self) -> list[dict[str, Any]]:
        """Return the newest reports with their headline figures."""
        return [_summary(record) for record in self._store.newest(LIST_LIMIT)]

    def get(self, report_id: str) -> dict[str, Any]:
        """Return one report with its full document."""
        record = self._store.get(report_id)
        if record is None:
            raise UnknownBenchmarkReportError("Record not found.")
        return {**_summary(record), "report": record.document}


def _record(
    report_id: str, created_at: datetime, document: Mapping[str, Any]
) -> BenchmarkReportRecord:
    """Read the identifying fields of a report, rejecting malformed ones."""
    judge = document.get("judge")
    if not isinstance(judge, Mapping):
        raise InvalidBenchmarkReportError("The report has no judge section.")
    model = judge.get("model")
    fingerprint = judge.get("rubric_fingerprint")
    quantization = judge.get("quantization")
    split = document.get("split")
    trials = document.get("trials")
    cases = document.get("cases")
    if not isinstance(model, str) or not model.strip():
        raise InvalidBenchmarkReportError("The report names no judge model.")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise InvalidBenchmarkReportError("The report has no rubric version.")
    if quantization is not None and not isinstance(quantization, str):
        raise InvalidBenchmarkReportError("The quantization must be text.")
    if split not in SPLITS:
        raise InvalidBenchmarkReportError("The report split is unknown.")
    return BenchmarkReportRecord(
        report_id=report_id,
        created_at=created_at,
        judge_model=model,
        quantization=quantization,
        split=split,
        trials=_positive_integer(trials, "trial count"),
        cases=_positive_integer(cases, "case count"),
        rubric_fingerprint=fingerprint,
        document=dict(document),
    )


def _positive_integer(value: object, name: str) -> int:
    """Accept whole numbers above zero, but not booleans."""
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    raise InvalidBenchmarkReportError(f"The report needs a positive {name}.")


def _content_hash(document: Mapping[str, Any]) -> str:
    """Hash the canonical JSON so identical reports are recognized."""
    canonical = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _summary(record: BenchmarkReportRecord) -> dict[str, Any]:
    """Pick the figures a comparison table shows from a stored report."""
    document = record.document
    attack = document.get("attack_success") or {}
    true_scores = (attack.get("labels") or {}).get("TRUE") or {}
    return {
        "report_id": record.report_id,
        "created_at": record.created_at.isoformat(),
        "judge_model": record.judge_model,
        "quantization": record.quantization,
        "split": record.split,
        "trials": record.trials,
        "cases": record.cases,
        "rubric_fingerprint": record.rubric_fingerprint,
        "category_kappa": {
            axis: summary.get("kappa")
            for axis, summary in (document.get("category") or {}).items()
        },
        "attack_recall": true_scores.get("recall"),
        "cases_per_hour": (document.get("cost") or {}).get("cases_per_hour"),
        "passes_gate": (document.get("gate") or {}).get("passes"),
    }
