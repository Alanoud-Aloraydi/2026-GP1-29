"""Persist published judge benchmark reports."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from harass.application.ports.judge_benchmark_store import JudgeBenchmarkStore
from harass.domain.judge_benchmark_report import BenchmarkReportRecord
from harass.infrastructure.persistence.session_factory import SessionFactory
from harass.infrastructure.persistence.tables import JudgeBenchmarkReportRow


class SqlAlchemyJudgeBenchmarkStore(JudgeBenchmarkStore):
    """Keep each distinct report once, identified by its content hash."""

    def __init__(self, session_factory: SessionFactory) -> None:
        """Bind the database-session factory."""
        self._sessions = session_factory

    def add(self, record: BenchmarkReportRecord, content_hash: str) -> str:
        """Insert the report, or return the id of an identical earlier one."""
        try:
            with self._sessions() as database, database.begin():
                database.add(
                    JudgeBenchmarkReportRow(
                        report_id=record.report_id,
                        created_at=record.created_at,
                        judge_model=record.judge_model,
                        quantization=record.quantization,
                        split=record.split,
                        trials=record.trials,
                        cases=record.cases,
                        rubric_fingerprint=record.rubric_fingerprint,
                        content_hash=content_hash,
                        document=record.document,
                    )
                )
        except IntegrityError:
            with self._sessions() as database:
                existing = database.scalar(
                    select(JudgeBenchmarkReportRow.report_id).where(
                        JudgeBenchmarkReportRow.content_hash == content_hash
                    )
                )
            if existing is None:
                raise
            return str(existing)
        return record.report_id

    def newest(self, limit: int) -> list[BenchmarkReportRecord]:
        """Read the most recently published reports."""
        with self._sessions() as database:
            rows = database.scalars(
                select(JudgeBenchmarkReportRow)
                .order_by(JudgeBenchmarkReportRow.created_at.desc())
                .limit(limit)
            )
            return [_record(row) for row in rows]

    def get(self, report_id: str) -> BenchmarkReportRecord | None:
        """Read one report by identifier."""
        with self._sessions() as database:
            row = database.get(JudgeBenchmarkReportRow, report_id)
            return _record(row) if row else None


def _record(row: JudgeBenchmarkReportRow) -> BenchmarkReportRecord:
    """Rebuild a report from its stored row."""
    return BenchmarkReportRecord(
        report_id=str(row.report_id),
        created_at=row.created_at,
        judge_model=row.judge_model,
        quantization=row.quantization,
        split=row.split,
        trials=row.trials,
        cases=row.cases,
        rubric_fingerprint=row.rubric_fingerprint,
        document=row.document,
    )
