"""Tests for publishing and reading judge benchmark reports."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from harass.application.errors import (
    InvalidBenchmarkReportError,
    UnknownBenchmarkReportError,
)
from harass.application.judge_benchmark_reports import JudgeBenchmarkReports
from harass.infrastructure.persistence.sqlalchemy_judge_benchmarks import (
    SqlAlchemyJudgeBenchmarkStore,
)
from harass.infrastructure.persistence.tables import JudgeBenchmarkReportRow


def report(**overrides: object) -> dict[str, Any]:
    """Build a report document as the benchmark command prints it."""
    document: dict[str, Any] = {
        "judge": {
            "model": "deepseek-r1:8b",
            "quantization": "Q4_K_M",
            "rubric_fingerprint": "520408242e9f",
        },
        "split": "dev",
        "trials": 1,
        "cases": 135,
        "category": {"OR": {"kappa": 0.74}, "AT": {"kappa": 0.51}},
        "attack_success": {"labels": {"TRUE": {"recall": 0.82}}},
        "cost": {"cases_per_hour": 47.4},
        "gate": {"passes": False},
    }
    document.update(overrides)
    return document


def ticking_clock() -> Callable[[], datetime]:
    """Return a clock that advances one minute per reading."""
    moment = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    readings = [0]

    def clock() -> datetime:
        """Advance and read the clock."""
        readings[0] += 1
        return moment + timedelta(minutes=readings[0])

    return clock


@pytest.fixture
def reports(database_factory: sessionmaker[Session]) -> JudgeBenchmarkReports:
    """Return the service over an isolated database."""
    return JudgeBenchmarkReports(
        SqlAlchemyJudgeBenchmarkStore(database_factory), ticking_clock()
    )


def test_a_published_report_round_trips_with_its_summary(
    reports: JudgeBenchmarkReports,
) -> None:
    """The stored document comes back unchanged beside its headline figures."""
    document = report()

    stored = reports.get(reports.publish(document))

    assert stored["report"] == document
    assert stored["judge_model"] == "deepseek-r1:8b"
    assert stored["quantization"] == "Q4_K_M"
    assert stored["category_kappa"] == {"OR": 0.74, "AT": 0.51}
    assert stored["attack_recall"] == 0.82
    assert stored["cases_per_hour"] == 47.4
    assert stored["passes_gate"] is False


def test_summaries_list_the_newest_first_without_documents(
    reports: JudgeBenchmarkReports,
) -> None:
    """The comparison list is cheap: no full documents, newest on top."""
    older = reports.publish(report())
    newer = reports.publish(report(split="test"))

    listed = reports.summaries()

    assert [item["report_id"] for item in listed] == [newer, older]
    assert all("report" not in item for item in listed)


def test_publishing_the_same_content_twice_stores_it_once(
    reports: JudgeBenchmarkReports,
) -> None:
    """Re-publishing a file is harmless and returns the first identifier."""
    first = reports.publish(report())

    assert reports.publish(report()) == first
    assert len(reports.summaries()) == 1


def test_changed_content_is_a_new_report(
    reports: JudgeBenchmarkReports,
) -> None:
    """A different run of the same judge is kept separately."""
    first = reports.publish(report())

    assert reports.publish(report(cases=136)) != first
    assert len(reports.summaries()) == 2


def test_a_partial_document_still_has_a_summary(
    reports: JudgeBenchmarkReports,
) -> None:
    """Missing metrics show as empty rather than failing the list."""
    document = report()
    for key in ("attack_success", "cost", "gate", "category"):
        del document[key]

    summary = reports.get(reports.publish(document))

    assert summary["category_kappa"] == {}
    assert summary["attack_recall"] is None
    assert summary["cases_per_hour"] is None
    assert summary["passes_gate"] is None


@pytest.mark.parametrize(
    "document",
    [
        report(judge=None),
        report(judge={"model": "", "rubric_fingerprint": "x"}),
        report(judge={"model": "m"}),
        report(
            judge={
                "model": "m",
                "rubric_fingerprint": "x",
                "quantization": 4,
            }
        ),
        report(split="everything"),
        report(trials=0),
        report(cases=True),
        report(cases="135"),
    ],
)
def test_malformed_reports_are_rejected(
    reports: JudgeBenchmarkReports, document: dict[str, Any]
) -> None:
    """Only a report with the fields the site shows can be published."""
    with pytest.raises(InvalidBenchmarkReportError):
        reports.publish(document)

    assert reports.summaries() == []


def test_reading_an_unknown_report_fails(
    reports: JudgeBenchmarkReports,
) -> None:
    """A missing identifier is a not-found error, not an empty result."""
    with pytest.raises(UnknownBenchmarkReportError):
        reports.get(str(uuid4()))


def test_database_rejects_an_unknown_split(
    database_factory: sessionmaker[Session],
) -> None:
    """The database is the last line of defence against a bad split."""
    with (
        pytest.raises(IntegrityError),
        database_factory() as database,
        database.begin(),
    ):
        database.add(
            JudgeBenchmarkReportRow(
                report_id=str(uuid4()),
                created_at=datetime.now(UTC),
                judge_model="m",
                split="bogus",
                trials=1,
                cases=1,
                rubric_fingerprint="f",
                content_hash="h",
                document={},
            )
        )
