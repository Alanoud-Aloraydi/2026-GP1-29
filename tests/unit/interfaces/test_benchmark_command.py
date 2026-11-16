"""Tests for the judge benchmark command."""

import io
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from harass.application.errors import GoldSetError, InvalidBenchmarkReportError
from harass.domain.judge_benchmark import (
    AttackVerdict,
    GoldCase,
    Split,
    split_of,
)
from harass.domain.taxonomy import Axis, ResponseCategory
from harass.interfaces.cli.benchmark_command import (
    RunOptions,
    run_benchmark_command,
)


def gold_case(family: str, *, hard: bool = False) -> GoldCase:
    """Build a gold case in the given family."""
    return GoldCase(
        key=f"{family}|MSA",
        family=family,
        axis=Axis.OVER_REFUSAL,
        dialect="MSA",
        request="q",
        response="a",
        criterion=None,
        category=ResponseCategory.PARTIAL_REFUSAL
        if hard
        else ResponseCategory.FULL_COMPLIANCE,
        attack_success=AttackVerdict.ABSTAIN if hard else None,
        truncated=False,
    )


async def unused_run(*args: object) -> dict[str, Any]:
    """Stand in for a judge run that must never happen."""
    raise AssertionError("The judge must not run.")


def unused_publish(path: Path) -> str:
    """Stand in for a publication that must never happen."""
    raise AssertionError("Nothing may be published.")


def families_by_split() -> tuple[str, str]:
    """Return one development family and one test family."""
    names = [f"m|{index:04d}" for index in range(40)]
    development = next(n for n in names if split_of(n) is Split.DEVELOPMENT)
    test = next(n for n in names if split_of(n) is Split.TEST)
    return development, test


async def invoke(
    argv: list[str],
    *,
    load: Callable[[Path], list[GoldCase]] = lambda path: [],
    run: Callable[..., Any] = unused_run,
    annotate: Callable[[list[GoldCase], Path], None] = lambda cases, path: (
        None
    ),
    publish: Callable[[Path], str] = unused_publish,
) -> tuple[int, str]:
    """Run the command with stand-ins and return its status and output."""
    output = io.StringIO()
    status = await run_benchmark_command(
        argv, load, run, annotate, publish, output
    )
    return status, output.getvalue()


async def test_run_judges_only_the_requested_split() -> None:
    """The test split excludes development families."""
    development, test = families_by_split()
    cases = [gold_case(development), gold_case(test)]
    seen: list[Any] = []

    async def run(
        selected: list[GoldCase], options: RunOptions
    ) -> dict[str, Any]:
        seen.append(
            (
                [case.family for case in selected],
                options.trials,
                options.split,
                options.quantization,
                options.judge,
            )
        )
        return {"cases": len(selected)}

    status, text = await invoke(
        ["run", "--gold", "gold.xlsx", "--split", "test", "--trials", "3"],
        load=lambda path: cases,
        run=run,
    )

    assert status == 0
    assert seen == [([test], 3, "test", None, "qwenguard")]
    assert json.loads(text) == {"cases": 1}


async def test_quantization_is_passed_to_the_run() -> None:
    """The judge's quantization is recorded with the report."""
    development, _ = families_by_split()
    seen: list[str | None] = []

    async def run(
        selected: list[GoldCase], options: RunOptions
    ) -> dict[str, Any]:
        seen.append(options.quantization)
        return {}

    status, _ = await invoke(
        [
            "run",
            "--gold",
            "gold.xlsx",
            "--split",
            "dev",
            "--quantization",
            "Q4_K_M",
        ],
        load=lambda path: [gold_case(development)],
        run=run,
    )

    assert status == 0
    assert seen == ["Q4_K_M"]


async def test_run_requires_an_explicit_split() -> None:
    """Running without a split is a usage error, never a silent default."""
    try:
        await invoke(["run", "--gold", "gold.xlsx"])
    except SystemExit as exit_request:
        assert exit_request.code == 2
    else:
        raise AssertionError("A missing split must be rejected.")


async def test_an_empty_split_is_an_error() -> None:
    """No cases in the split stops before calling the judge."""
    development, _ = families_by_split()

    status, text = await invoke(
        ["run", "--gold", "gold.xlsx", "--split", "test"],
        load=lambda path: [gold_case(development)],
    )

    assert status == 1
    assert "no cases" in text


async def test_prepare_annotation_writes_the_chosen_families() -> None:
    """Hard families go to the blind sheet along with the sampled quota."""
    cases = [gold_case(f"m|{index:04d}") for index in range(10)]
    cases.append(gold_case("m|hard", hard=True))
    written: list[tuple[list[str], Path]] = []

    status, text = await invoke(
        [
            "prepare-annotation",
            "--gold",
            "gold.xlsx",
            "--output",
            "sheet.csv",
            "--fraction",
            "0.3",
        ],
        load=lambda path: cases,
        annotate=lambda selected, path: written.append(
            ([case.family for case in selected], path)
        ),
    )

    assert status == 0
    families, destination = written[0]
    assert "m|hard" in families
    assert len(families) == 4
    assert destination == Path("sheet.csv")
    assert "all labels are blank" in text


async def test_gold_set_errors_are_reported() -> None:
    """A bad workbook prints a benchmark error instead of a traceback."""

    def load(path: Path) -> list[GoldCase]:
        raise GoldSetError("Sheet 'Attack' is missing.")

    status, text = await invoke(
        ["run", "--gold", "g.xlsx", "--split", "all"], load=load
    )

    assert status == 1
    assert "Benchmark error: Sheet 'Attack' is missing." in text


async def test_limit_per_axis_keeps_cases_of_both_axes() -> None:
    """A smoke run takes the first cases of each axis, not of the file."""
    cases = [
        replace(gold_case(f"m|{index:04d}"), axis=axis)
        for index, axis in enumerate(
            [Axis.OVER_REFUSAL] * 3 + [Axis.ADVERSARIAL] * 3
        )
    ]
    selected_axes: list[Axis] = []

    async def run(
        selected: list[GoldCase], options: RunOptions
    ) -> dict[str, Any]:
        selected_axes.extend(case.axis for case in selected)
        return {}

    status, _ = await invoke(
        ["run", "--gold", "g.xlsx", "--split", "all", "--limit-per-axis", "2"],
        load=lambda path: cases,
        run=run,
    )

    assert status == 0
    assert selected_axes == [Axis.OVER_REFUSAL] * 2 + [Axis.ADVERSARIAL] * 2


async def test_publish_stores_the_report_and_names_it() -> None:
    """Publishing needs no gold set and prints the new report's id."""
    published: list[Path] = []

    def publish(path: Path) -> str:
        published.append(path)
        return "report-1"

    status, text = await invoke(
        ["publish", "--report", "report.json"], publish=publish
    )

    assert status == 0
    assert published == [Path("report.json")]
    assert "Published judge benchmark report report-1." in text


async def test_publish_failures_are_reported() -> None:
    """A malformed report or file prints an error instead of a traceback."""

    def malformed(path: Path) -> str:
        raise InvalidBenchmarkReportError("The report names no judge model.")

    def unreadable(path: Path) -> str:
        raise json.JSONDecodeError("Expecting value", "", 0)

    for publish in (malformed, unreadable):
        status, text = await invoke(
            ["publish", "--report", "report.json"], publish=publish
        )

        assert status == 1
        assert "Benchmark error:" in text


async def test_the_judge_kind_is_chosen_on_the_command_line() -> None:
    """Each judge is selected by name; Qwen3Guard is the default."""
    development, _ = families_by_split()
    judges: list[str] = []

    async def run(
        selected: list[GoldCase], options: RunOptions
    ) -> dict[str, Any]:
        judges.append(options.judge)
        return {}

    for extra in (
        [],
        ["--judge", "d1"],
        ["--judge", "faisal"],
        ["--judge", "qwenguard"],
        ["--judge", "qwenguard-small"],
        ["--judge", "escalating"],
    ):
        status, _ = await invoke(
            ["run", "--gold", "gold.xlsx", "--split", "dev", *extra],
            load=lambda path: [gold_case(development)],
            run=run,
        )
        assert status == 0

    assert judges == [
        "qwenguard",
        "d1",
        "faisal",
        "qwenguard",
        "qwenguard-small",
        "escalating",
    ]


async def test_an_unknown_judge_kind_is_rejected() -> None:
    """Only the known judge kinds are accepted."""
    try:
        await invoke(
            ["run", "--gold", "g.xlsx", "--split", "dev", "--judge", "x"]
        )
    except SystemExit as exit_request:
        assert exit_request.code == 2
    else:
        raise AssertionError("An unknown judge must be rejected.")
