"""Tests for the evaluate command of the command-line interface."""

import io
from pathlib import Path

import pytest

from harass.application.errors import NoMatchingCasesError
from harass.application.evaluation_report import EvaluationReport, EvaluationRequest
from harass.application.ports.evaluation_journal import EvaluationJournal
from harass.application.ports.report_exporter import ReportExporter
from harass.application.use_cases.run_evaluation import RunEvaluation
from harass.domain.errors import InvalidCaseSelectionError, InvalidTargetConnectionError
from harass.domain.metrics import compute_metrics
from harass.domain.taxonomy import ArabicVariety, Axis, BypassStrategy
from harass.interfaces.cli.evaluate_command import (
    EvaluateCommand,
    build_request,
    parse_command,
    run_evaluate_command,
)

ENVIRONMENT = {
    "HARASS_TARGET_BASE_URL": "https://env.invalid/v1",
    "HARASS_TARGET_MODEL": "env-model",
    "HARASS_TARGET_API_KEY": "secret",
}
REPORT = EvaluationReport(
    run_identifier="run",
    target_model="env-model",
    variant_names=(),
    include_baseline=True,
    outcomes=(),
    metrics=compute_metrics([]),
)


class StubUseCase(RunEvaluation):
    """Records the request and returns a fixed report or error."""

    def __init__(self, error: Exception | None = None) -> None:
        """Remember the error to raise, if any."""
        self.requests: list[EvaluationRequest] = []
        self._error = error

    async def execute(
        self, request: EvaluationRequest, *, journal: EvaluationJournal | None = None
    ) -> EvaluationReport:
        """Record the request, then fail or return the fixed report."""
        self.requests.append(request)
        if self._error:
            raise self._error
        return REPORT


class RecordingExporter(ReportExporter):
    """Records the destinations written to."""

    def __init__(self) -> None:
        """Start with no recorded destinations."""
        self.destinations: list[Path] = []

    def export(self, report: EvaluationReport, destination: Path) -> None:
        """Record the destination."""
        self.destinations.append(destination)


def command(*arguments: str) -> EvaluateCommand:
    """Parse a command line that always names an output file."""
    return parse_command(["--output", "report.json", *arguments])


def test_defaults_select_everything_from_the_environment_target() -> None:
    """Without options every case and chain is evaluated, with the baseline."""
    request = build_request(command(), ENVIRONMENT)

    assert request.target.base_url == "https://env.invalid/v1"
    assert request.target.model_name == "env-model"
    assert request.variant_selection.template_names is None
    assert request.include_baseline
    assert request.max_base_cases_per_axis is None


def test_options_override_the_environment_and_restrict_the_run() -> None:
    """Options map onto the selection, chains, sampling and connection."""
    request = build_request(
        command(
            "--target-model",
            "other-model",
            "--max-requests-per-minute",
            "28",
            "--axis",
            "AT",
            "--variety",
            "NAJ",
            "--variety",
            "EGY",
            "--strategy",
            "OBF",
            "--template",
            "at_obfuscation_quoted",
            "--transform",
            "base64",
            "--no-baseline",
            "--max-base-cases-per-axis",
            "3",
            "--sampling-seed",
            "9",
        ),
        ENVIRONMENT,
    )

    assert request.target.model_name == "other-model"
    assert request.target.max_requests_per_minute == 28
    assert request.selection.axis is Axis.ADVERSARIAL
    assert request.selection.varieties == {ArabicVariety("NAJ"), ArabicVariety("EGY")}
    assert request.selection.strategies == {BypassStrategy("OBF")}
    assert request.variant_selection.template_names == ("at_obfuscation_quoted",)
    assert request.variant_selection.transform_names == ("base64",)
    assert not request.include_baseline
    assert (request.max_base_cases_per_axis, request.sampling_seed) == (3, 9)


def test_baseline_only_selects_no_chain() -> None:
    """The baseline-only switch is an explicit empty chain selection."""
    assert (
        build_request(command("--baseline-only"), ENVIRONMENT).variant_selection.template_names
        == ()
    )
    assert (
        build_request(command("--baseline-only"), ENVIRONMENT).variant_selection.transform_names
        == ()
    )


def test_contradictory_switches_are_rejected() -> None:
    """Disabling both the chains and the baseline would send nothing."""
    with pytest.raises(SystemExit):
        command("--baseline-only", "--no-baseline")


def test_missing_api_key_is_a_domain_error() -> None:
    """The key comes only from the environment, never from the command line."""
    with pytest.raises(InvalidTargetConnectionError):
        build_request(command(), {**ENVIRONMENT, "HARASS_TARGET_API_KEY": ""})


def test_strategies_cannot_restrict_over_refusal_cases() -> None:
    """Over-refusal cases carry no strategy."""
    with pytest.raises(InvalidCaseSelectionError):
        build_request(command("--axis", "OR", "--strategy", "DIR"), ENVIRONMENT)


async def test_successful_run_exports_and_presents_the_report() -> None:
    """The report is written to the requested path and summarized on the console."""
    exporter = RecordingExporter()
    output = io.StringIO()

    status = await run_evaluate_command(
        command(), ENVIRONMENT, lambda _: StubUseCase(), exporter, output
    )

    assert status == 0
    assert exporter.destinations == [Path("report.json")]
    assert "Report written to report.json" in output.getvalue()


async def test_failed_run_reports_the_error_without_exporting() -> None:
    """Application errors become a message and a non-zero status."""
    exporter = RecordingExporter()
    output = io.StringIO()

    status = await run_evaluate_command(
        command(),
        ENVIRONMENT,
        lambda _: StubUseCase(NoMatchingCasesError("No evaluation case matches.")),
        exporter,
        output,
    )

    assert status == 1
    assert exporter.destinations == []
    assert "No evaluation case matches." in output.getvalue()
