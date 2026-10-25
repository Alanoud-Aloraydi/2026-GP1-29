"""Export of evaluation reports as UTF-8 JSON files."""

import json
from pathlib import Path

from harass.application.errors import ReportExportError
from harass.application.evaluation.contracts import EvaluationReport
from harass.application.ports.report_exporter import ReportExporter
from harass.application.reporting.document import report_document


class JsonReportExporter(ReportExporter):
    """Export coded report data with Arabic display labels."""

    def export(self, report: EvaluationReport, destination: Path) -> None:
        """Write the report, replacing any existing file at the destination."""
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(
                    report_document(report), ensure_ascii=False, indent=2
                )
                + "\n",
                encoding="utf-8",
            )
        except OSError as error:
            raise ReportExportError(
                f"Cannot write the report to {destination}: {error}"
            ) from error
