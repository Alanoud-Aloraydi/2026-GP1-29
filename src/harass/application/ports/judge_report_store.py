"""Persistence contract for published judge benchmark reports."""

from abc import ABC, abstractmethod

from harass.domain.judge_report import JudgeReportRecord


class JudgeReportStore(ABC):
    """Persist published reports without altering them."""

    @abstractmethod
    def add(self, record: JudgeReportRecord, content_hash: str) -> str:
        """Store a report and return its identifier.

        When a report with the same content hash exists, nothing is stored
        and the identifier of the existing report is returned.
        """

    @abstractmethod
    def newest(self, limit: int) -> list[JudgeReportRecord]:
        """Return up to limit reports, newest first."""

    @abstractmethod
    def get(self, report_id: str) -> JudgeReportRecord | None:
        """Return one report, or none when it does not exist."""
