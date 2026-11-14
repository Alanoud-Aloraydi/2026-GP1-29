"""Persistence contract for judge benchmark reports."""

from abc import ABC, abstractmethod

from harass.domain.judge_benchmark_report import BenchmarkReportRecord


class JudgeBenchmarkStore(ABC):
    """Persist published benchmark reports without altering them."""

    @abstractmethod
    def add(self, record: BenchmarkReportRecord, content_hash: str) -> str:
        """Store a report and return its identifier.

        When a report with the same content hash exists, nothing is stored
        and the identifier of the existing report is returned.
        """

    @abstractmethod
    def newest(self, limit: int) -> list[BenchmarkReportRecord]:
        """Return up to limit reports, newest first."""

    @abstractmethod
    def get(self, report_id: str) -> BenchmarkReportRecord | None:
        """Return one report, or none when it does not exist."""
