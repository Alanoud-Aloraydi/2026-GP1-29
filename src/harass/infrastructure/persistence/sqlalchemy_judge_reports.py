"""Persist published judge benchmark reports."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from harass.application.ports.judge_report_store import JudgeReportStore
from harass.domain.judge_report import JudgeReportRecord
from harass.infrastructure.persistence.session_factory import SessionFactory
from harass.infrastructure.persistence.tables import JudgeBenchmarkReportRow


class SqlAlchemyJudgeReportStore(JudgeReportStore):
    """Keep each distinct report once, identified by its content hash."""

    def __init__(self, factory: SessionFactory) -> None:
        """Bind the session factory."""
        self._factory = factory

    def add(self, record: JudgeReportRecord, content_hash: str) -> str:
        """Insert the report, or return the id of an identical earlier one."""
        # The record's fields share their names with the table columns.
        row = JudgeBenchmarkReportRow(**vars(record), content_hash=content_hash)
        try:
            with self._factory() as session, session.begin():
                session.add(row)
        except IntegrityError:
            with self._factory() as session:
                existing = session.scalar(
                    select(JudgeBenchmarkReportRow.report_id).where(
                        JudgeBenchmarkReportRow.content_hash == content_hash
                    )
                )
            if existing is None:
                raise
            return str(existing)
        return record.report_id

    def newest(self, limit: int) -> list[JudgeReportRecord]:
        """Read the most recently published reports."""
        with self._factory() as session:
            rows = session.scalars(
                select(JudgeBenchmarkReportRow)
                .order_by(JudgeBenchmarkReportRow.created_at.desc())
                .limit(limit)
            )
            return [_record(row) for row in rows]

    def get(self, report_id: str) -> JudgeReportRecord | None:
        """Read one report by identifier."""
        with self._factory() as session:
            row = session.get(JudgeBenchmarkReportRow, report_id)
            return _record(row) if row else None


def _record(row: JudgeBenchmarkReportRow) -> JudgeReportRecord:
    """Map a stored row back to its record."""
    return JudgeReportRecord(
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
