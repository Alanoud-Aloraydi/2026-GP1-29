"""Publish judge benchmark reports and read them for administrators."""

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from harass.application.errors import InvalidBenchmarkReportError, UnknownBenchmarkReportError
from harass.application.ports.judge_report_store import JudgeReportStore
from harass.domain.judge_report import JudgeReportRecord

LIST_LIMIT = 100
SPLITS = frozenset({"dev", "test", "all"})

type Document = Mapping[str, Any]


class JudgeReports:
    """Validate, store and summarize judge benchmark reports."""

    def __init__(
        self, store: JudgeReportStore, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    ) -> None:
        """Bind the store and the clock that stamps new reports."""
        self._store = store
        self._clock = clock

    def publish(self, document: Document) -> str:
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


def _record(report_id: str, created_at: datetime, document: Document) -> JudgeReportRecord:
    """Read the identifying fields of a report, rejecting malformed ones."""
    judge = document.get("judge")
    if not isinstance(judge, Mapping):
        raise InvalidBenchmarkReportError("The report has no judge section.")
    model, fingerprint = judge.get("model"), judge.get("rubric_fingerprint")
    quantization = judge.get("quantization")
    if not isinstance(model, str) or not model.strip():
        raise InvalidBenchmarkReportError("The report names no judge model.")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise InvalidBenchmarkReportError("The report has no rubric version.")
    if quantization is not None and not isinstance(quantization, str):
        raise InvalidBenchmarkReportError("The quantization must be text.")
    if document.get("split") not in SPLITS:
        raise InvalidBenchmarkReportError("The report split is unknown.")
    return JudgeReportRecord(
        report_id=report_id,
        created_at=created_at,
        judge_model=model,
        quantization=quantization,
        split=document["split"],
        trials=_positive_integer(document.get("trials"), "trial count"),
        cases=_positive_integer(document.get("cases"), "case count"),
        rubric_fingerprint=fingerprint,
        document=dict(document),
    )


def _summary(record: JudgeReportRecord) -> dict[str, Any]:
    """Pick the figures the judge comparison table shows."""
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
            axis: summary.get("kappa") for axis, summary in (document.get("category") or {}).items()
        },
        "attack_recall": true_scores.get("recall"),
        "cases_per_hour": (document.get("cost") or {}).get("cases_per_hour"),
        "passes_gate": (document.get("gate") or {}).get("passes"),
    }


def _positive_integer(value: object, name: str) -> int:
    """Accept whole numbers above zero, but not booleans."""
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    raise InvalidBenchmarkReportError(f"The report needs a positive {name}.")


def _content_hash(document: Document) -> str:
    """Hash the canonical JSON so identical reports are recognized."""
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
