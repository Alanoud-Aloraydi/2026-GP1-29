"""Read-only judge benchmark endpoints for administrators."""

from typing import Any

from fastapi import APIRouter, Depends

from harass.application.errors import UnknownBenchmarkReportError
from harass.application.judge_reports import JudgeReports
from harass.interfaces.api.accounts.dependencies import administrator
from harass.interfaces.api.identifiers import validated_identifier


def admin_router(reports: JudgeReports) -> APIRouter:
    """List and read judge benchmark reports, for administrators only."""
    router = APIRouter(prefix="/admin/judge-benchmarks", dependencies=[Depends(administrator)])

    @router.get("")
    def list_reports() -> list[dict[str, Any]]:
        """Return the newest published reports."""
        return reports.summaries()

    @router.get("/{report_id}")
    def get_report(report_id: str) -> dict[str, Any]:
        """Return one report with its full document."""
        return reports.get(validated_identifier(report_id, UnknownBenchmarkReportError))

    return router
