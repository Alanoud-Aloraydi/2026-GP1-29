"""Port for persisting evaluation reports outside the system."""

from abc import ABC, abstractmethod
from pathlib import Path

from harass.application.evaluation_report import EvaluationReport


class ReportExporter(ABC):
    """Writes an evaluation report to a destination."""

    @abstractmethod
    def export(self, report: EvaluationReport, destination: Path) -> None:
        """Write the report, replacing any existing file at the destination.

        Raises:
            ReportExportError: If the report cannot be written.
        """
