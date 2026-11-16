"""Read-only judge benchmark endpoints for administrators."""

from typing import Any

from fastapi import Depends, FastAPI

from harass.application.errors import UnknownBenchmarkReportError
from harass.application.judge_benchmark_reports import JudgeBenchmarkReports
from harass.interfaces.api.accounts.dependencies import administrator
from harass.interfaces.api.evaluations.mapping import validated_identifier


def install_admin_routes(app: FastAPI, reports: JudgeBenchmarkReports) -> None:
    """Register the administrator endpoints with their injected service."""
    guard = [Depends(administrator)]

    @app.get("/admin/judge-benchmarks", dependencies=guard)
    def list_reports() -> list[dict[str, Any]]:
        """Return the newest published benchmark reports."""
        return reports.summaries()

    @app.get("/admin/judge-benchmarks/{report_id}", dependencies=guard)
    def get_report(report_id: str) -> dict[str, Any]:
        """Return one benchmark report with its full document."""
        return reports.get(
            validated_identifier(report_id, UnknownBenchmarkReportError)
        )
