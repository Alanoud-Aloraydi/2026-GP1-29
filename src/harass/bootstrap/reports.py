"""Composition root of the judge report publishing command."""

import json
import os
import sys
from pathlib import Path
from typing import Any

from harass.application.judge_reports import JudgeReports
from harass.bootstrap.database import database_sessions, load_environment
from harass.infrastructure.persistence.sqlalchemy_judge_reports import SqlAlchemyJudgeReportStore
from harass.infrastructure.settings import BackendSettings
from harass.interfaces.cli.report_command import run_report_command


def _documents(report_file: Path) -> list[dict[str, Any]]:
    """Read one report, or a list of reports, from a JSON file."""
    content = json.loads(report_file.read_text(encoding="utf-8-sig"))
    documents = content if isinstance(content, list) else [content]
    if not all(isinstance(document, dict) for document in documents):
        raise ValueError("Each report must be a JSON object.")
    return documents


def _publish(report_file: Path) -> list[str]:
    """Store every report in the file for the administrator page."""
    documents = _documents(report_file)
    database_url = BackendSettings.from_environment(os.environ).database_url
    with database_sessions(database_url) as factory:
        reports = JudgeReports(SqlAlchemyJudgeReportStore(factory))
        return [reports.publish(document) for document in documents]


def main() -> None:
    """Entry point of the ``harass-reports`` command."""
    load_environment()
    # A missing setting is a ValueError, which the command reports itself.
    sys.exit(run_report_command(sys.argv[1:], _publish, sys.stdout))


if __name__ == "__main__":
    main()
