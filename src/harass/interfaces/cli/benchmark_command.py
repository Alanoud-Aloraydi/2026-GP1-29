"""Judge benchmark commands with their collaborators injected."""

import argparse
import json
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from harass.application.errors import ApplicationError
from harass.domain.errors import DomainError
from harass.domain.judge_benchmark import (
    ANNOTATION_FRACTION,
    GoldCase,
    annotation_families,
    split_of,
)
from harass.domain.taxonomy import Axis

ALL_CASES = "all"
SPLIT_CHOICES = ("dev", "test", ALL_CASES)
JUDGE_CHOICES = (
    "d1",
    "faisal",
    "qwenguard",
    "qwenguard-small",
    "escalating",
    "split",
    "shieldstral",
)


@dataclass(frozen=True)
class RunOptions:
    """How a benchmark run is configured, apart from its cases."""

    trials: int
    split: str
    quantization: str | None
    judge: str


type LoadCases = Callable[[Path], list[GoldCase]]
type RunBenchmark = Callable[
    [list[GoldCase], RunOptions], Awaitable[dict[str, Any]]
]
type WriteAnnotation = Callable[[list[GoldCase], Path], None]
type PublishReport = Callable[[Path], str]


async def run_benchmark_command(
    argv: Sequence[str],
    load: LoadCases,
    run: RunBenchmark,
    write_annotation: WriteAnnotation,
    publish: PublishReport,
    output: TextIO,
) -> int:
    """Benchmark a judge, prepare annotation sheets or publish a report."""
    arguments = _parser().parse_args(argv)
    try:
        if arguments.action == "publish":
            report_id = publish(arguments.report)
            message = f"Published judge benchmark report {report_id}."
        elif arguments.action == "run":
            selected = _in_split(load(arguments.gold), arguments.split)
            if arguments.limit_per_axis is not None:
                selected = _limit_per_axis(selected, arguments.limit_per_axis)
            if not selected:
                raise ValueError("the split has no cases.")
            options = RunOptions(
                arguments.trials,
                arguments.split,
                arguments.quantization,
                arguments.judge,
            )
            report = await run(selected, options)
            message = json.dumps(report, ensure_ascii=False, indent=2)
        else:
            cases = load(arguments.gold)
            chosen = set(annotation_families(cases, arguments.fraction))
            sheet = [case for case in cases if case.family in chosen]
            write_annotation(sheet, arguments.output)
            message = (
                f"Blind annotation sheet created for {len(chosen)} "
                "families; all labels are blank."
            )
    except (OSError, ApplicationError, DomainError, ValueError) as error:
        print(f"Benchmark error: {error}", file=output)
        return 1
    print(message, file=output)
    return 0


def _parser() -> argparse.ArgumentParser:
    """Describe the run, prepare-annotation and publish subcommands."""
    parser = argparse.ArgumentParser(prog="harass-judge-benchmark")
    commands = parser.add_subparsers(dest="action", required=True)
    run = commands.add_parser("run")
    run.add_argument("--gold", type=Path, required=True)
    run.add_argument("--split", choices=SPLIT_CHOICES, required=True)
    run.add_argument("--trials", type=int, default=1)
    run.add_argument("--limit-per-axis", type=int)
    run.add_argument("--quantization")
    run.add_argument("--judge", choices=JUDGE_CHOICES, default="qwenguard")
    annotate = commands.add_parser("prepare-annotation")
    annotate.add_argument("--gold", type=Path, required=True)
    annotate.add_argument("--output", type=Path, required=True)
    annotate.add_argument(
        "--fraction", type=float, default=ANNOTATION_FRACTION
    )
    publish = commands.add_parser("publish")
    publish.add_argument("--report", type=Path, required=True)
    return parser


def _limit_per_axis(cases: Sequence[GoldCase], limit: int) -> list[GoldCase]:
    """Keep the first cases of each axis, so a smoke run covers both judges."""
    kept: list[GoldCase] = []
    counts: Counter[Axis] = Counter()
    for case in cases:
        if counts[case.axis] < limit:
            counts[case.axis] += 1
            kept.append(case)
    return kept


def _in_split(cases: Sequence[GoldCase], split: str) -> list[GoldCase]:
    """Keep the cases of the requested split."""
    if split == ALL_CASES:
        return list(cases)
    return [case for case in cases if split_of(case.family).value == split]
