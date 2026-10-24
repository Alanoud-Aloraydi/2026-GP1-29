"""Command-line interface for single-turn evaluation runs."""

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from harass.application.errors import ApplicationError
from harass.application.evaluation.contracts import (
    EvaluationReport,
    EvaluationRequest,
)
from harass.application.evaluation.runner import RunEvaluation
from harass.application.ports.report_exporter import ReportExporter
from harass.application.reporting.labels import METRIC_LABELS
from harass.domain.case_selection import CaseSelection
from harass.domain.errors import DomainError
from harass.domain.metrics import Proportion
from harass.domain.prompt_variant import (
    AdaptiveSettings,
    EvaluationMode,
    VariantSelection,
)
from harass.domain.target_connection import TargetConnection
from harass.domain.taxonomy import (
    ArabicVariety,
    Axis,
    BypassStrategy,
    RiskCategory,
    SubjectDomain,
)

TARGET_API_KEY_VARIABLE = "HARASS_TARGET_API_KEY"
TARGET_BASE_URL_VARIABLE = "HARASS_TARGET_BASE_URL"
TARGET_MODEL_VARIABLE = "HARASS_TARGET_MODEL"


@dataclass(frozen=True)
class EvaluateCommand:
    """Represent parsed evaluation inputs and output settings."""

    dataset_file: Path
    output: Path
    arguments: argparse.Namespace


type UseCaseFactory = Callable[[EvaluateCommand], RunEvaluation]


def build_parser() -> argparse.ArgumentParser:
    """Return the parser of the evaluate command."""
    parser = argparse.ArgumentParser(
        prog="harass",
        description=(
            "Evaluate an OpenAI-compatible model on the "
            "adversarial and over-refusal axes. The API "
            "key is read from "
        )
        + TARGET_API_KEY_VARIABLE
        + ".",
    )
    target = parser.add_argument_group("model under evaluation")
    target.add_argument(
        "--target-base-url",
        help=f"Base URL; defaults to {TARGET_BASE_URL_VARIABLE}.",
    )
    target.add_argument(
        "--target-model",
        help=f"Model name; defaults to {TARGET_MODEL_VARIABLE}.",
    )
    target.add_argument(
        "--max-requests-per-minute", type=int, help="Request rate limit."
    )
    selection = parser.add_argument_group("case selection")
    selection.add_argument("--axis", choices=_codes(Axis))
    selection.add_argument(
        "--domain", action="append", choices=_codes(SubjectDomain)
    )
    selection.add_argument(
        "--risk-category", action="append", choices=_codes(RiskCategory)
    )
    selection.add_argument(
        "--variety", action="append", choices=_codes(ArabicVariety)
    )
    selection.add_argument(
        "--strategy",
        action="append",
        choices=_codes(BypassStrategy),
        help="Adversarial cases using at least one of these strategies.",
    )
    selection.add_argument(
        "--max-base-cases-per-axis",
        type=int,
        help=(
            "Sample this many base cases per axis, keeping "
            "every variety of each."
        ),
    )
    selection.add_argument(
        "--sampling-seed",
        type=int,
        default=0,
        help=(
            "Seed for case sampling and for any random "
            "transform, making runs reproducible."
        ),
    )
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--no-baseline", action="store_true")
    files = parser.add_argument_group("files")
    files.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/test_dataset.xlsx"),
        help="Dataset spreadsheet.",
    )
    files.add_argument(
        "--templates-directory", type=Path, default=Path("config/templates")
    )
    parser.add_argument(
        "--template",
        action="append",
        help="Eligible template name; repeatable.",
    )
    parser.add_argument(
        "--transform",
        action="append",
        help="Eligible transform name; repeatable.",
    )
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in EvaluationMode],
        default="adaptive",
    )
    parser.add_argument(
        "--attempt-budget",
        type=int,
        default=8,
        help="Adaptive target attempts per case, excluding baseline.",
    )
    files.add_argument(
        "--output", type=Path, required=True, help="JSON report to write."
    )
    return parser


def parse_command(argv: Sequence[str]) -> EvaluateCommand:
    """Parse CLI arguments and report invalid input through argparse."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.baseline_only and arguments.no_baseline:
        parser.error(
            "--baseline-only and --no-baseline leave nothing to send."
        )
    return EvaluateCommand(
        dataset_file=arguments.dataset,
        output=arguments.output,
        arguments=arguments,
    )


def build_request(
    command: EvaluateCommand, environment: Mapping[str, str]
) -> EvaluationRequest:
    """Build an evaluation request from CLI and environment settings.

    Raises: DomainError: If the target connection or the selection is invalid.
    """
    arguments = command.arguments
    target = TargetConnection(
        base_url=arguments.target_base_url
        or environment.get(TARGET_BASE_URL_VARIABLE, ""),
        model_name=arguments.target_model
        or environment.get(TARGET_MODEL_VARIABLE, ""),
        api_key=environment.get(TARGET_API_KEY_VARIABLE, ""),
        max_requests_per_minute=arguments.max_requests_per_minute,
    )
    selection = CaseSelection(
        axis=Axis(arguments.axis) if arguments.axis else None,
        subject_domains=frozenset(map(SubjectDomain, arguments.domain or ())),
        risk_categories=frozenset(
            map(RiskCategory, arguments.risk_category or ())
        ),
        varieties=frozenset(map(ArabicVariety, arguments.variety or ())),
        strategies=frozenset(map(BypassStrategy, arguments.strategy or ())),
    )
    return EvaluationRequest(
        target=target,
        selection=selection,
        include_baseline=not arguments.no_baseline,
        max_base_cases_per_axis=arguments.max_base_cases_per_axis,
        sampling_seed=arguments.sampling_seed,
        variant_selection=VariantSelection(
            ()
            if arguments.baseline_only
            else tuple(arguments.template)
            if arguments.template
            else None,
            ()
            if arguments.baseline_only
            else tuple(arguments.transform)
            if arguments.transform
            else None,
        ),
        adaptive_settings=AdaptiveSettings(
            EvaluationMode(arguments.mode),
            arguments.attempt_budget,
            arguments.sampling_seed,
        ),
    )


async def run_evaluate_command(
    command: EvaluateCommand,
    environment: Mapping[str, str],
    use_case_factory: UseCaseFactory,
    exporter: ReportExporter,
    output: TextIO,
) -> int:
    """Run one parsed evaluation command and return the process exit status."""
    try:
        request = build_request(command, environment)
        report = await use_case_factory(command).execute(request)
        exporter.export(report, command.output)
    except (ApplicationError, DomainError) as error:
        print(f"Error: {error}", file=output)
        return 1
    present_report(report, command.output, output)
    return 0


def present_report(
    report: EvaluationReport, destination: Path, output: TextIO
) -> None:
    """Print the headline metrics of a report."""
    metrics = report.metrics
    lines = [f"Run {report.run_identifier} on {report.target_model}"]
    for axis_name, summary in (
        ("AT", metrics.adversarial),
        ("OR", metrics.over_refusal),
    ):
        if summary is None:
            continue
        for name, proportion in vars(summary).items():
            lines.append(
                f"  {axis_name} {METRIC_LABELS[name]}: {_format(proportion)}"
            )
    for variant_name, gap in metrics.discrimination_gap_by_variant.items():
        lines.append(f"  Discrimination gap [{variant_name}]: {gap:+.3f}")
    for (
        risk_category,
        gap,
    ) in metrics.discrimination_gap_by_risk_category.items():
        lines.append(
            f"  Discrimination gap [risk {risk_category}]: {gap:+.3f}"
        )
    lines.append(f"  Unscored outcomes: {metrics.unscored_outcomes}")
    lines.append(f"Report written to {destination}")
    print("\n".join(lines), file=output)


def _format(proportion: Proportion) -> str:
    """Return a proportion as count, rate and 95% Wilson interval."""
    interval = proportion.wilson_interval()
    if proportion.rate is None or interval is None:
        return f"{proportion.count}/{proportion.total}"
    return (
        f"{proportion.count}/{proportion.total} = {proportion.rate:.3f} "
        f"(95% CI {interval[0]:.3f}-{interval[1]:.3f})"
    )


def _codes(
    code_type: type[
        Axis | SubjectDomain | RiskCategory | ArabicVariety | BypassStrategy
    ],
) -> list[str]:
    """Return the codes accepted for a taxonomy dimension."""
    return [member.value for member in code_type]
