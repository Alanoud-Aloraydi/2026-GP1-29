"""Judge benchmark reports published for administrators."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from harass.infrastructure.persistence.tables.base import ENTITY_ID, Base


class JudgeBenchmarkReportRow(Base):
    """One benchmark run of a judge against the gold set."""

    __tablename__ = "judge_benchmark_reports"
    __table_args__ = (
        CheckConstraint("split IN ('dev', 'test', 'all')", name="ck_judge_benchmark_reports_split"),
        CheckConstraint("trials >= 1", name="ck_judge_benchmark_reports_trials"),
        CheckConstraint("cases >= 1", name="ck_judge_benchmark_reports_cases"),
    )

    report_id: Mapped[str] = mapped_column(ENTITY_ID, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    document: Mapped[dict[str, Any]] = mapped_column(JSON)
    judge_model: Mapped[str] = mapped_column(String(200))
    quantization: Mapped[str | None] = mapped_column(String(64))
    split: Mapped[str] = mapped_column(String(8))
    trials: Mapped[int] = mapped_column(Integer)
    cases: Mapped[int] = mapped_column(Integer)
    rubric_fingerprint: Mapped[str] = mapped_column(String(32))
