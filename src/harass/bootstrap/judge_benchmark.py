"""Composition root of the judge benchmark command."""

import asyncio
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from harass.application.escalating_response_judge import (
    EscalatingResponseJudge,
)
from harass.application.judge_benchmark import benchmark_report, run_benchmark
from harass.application.judge_benchmark_reports import JudgeBenchmarkReports
from harass.application.ports.response_judge import ResponseJudge
from harass.application.split_response_judge import SplitResponseJudge
from harass.domain.judge_benchmark import GoldCase
from harass.infrastructure.dataset.gold_set_source import load_gold_cases
from harass.infrastructure.http.d1_response_judge import D1ResponseJudge
from harass.infrastructure.http.faisal_response_judge import (
    FaisalResponseJudge,
)
from harass.infrastructure.http.qwenguard_response_judge import (
    QwenGuardResponseJudge,
)
from harass.infrastructure.http.rubrics import (
    RUBRIC_DIRECTORY,
    Rubrics,
    load_rubrics,
    rubric_fingerprint,
)
from harass.infrastructure.http.shieldstral_response_judge import (
    ShieldstralResponseJudge,
)
from harass.infrastructure.persistence.schema import require_current_schema
from harass.infrastructure.persistence.sqlalchemy_judge_benchmarks import (
    SqlAlchemyJudgeBenchmarkStore,
)
from harass.infrastructure.reporting.annotation_sheet import (
    write_annotation_sheet,
)
from harass.infrastructure.settings import BackendSettings, SettingsError
from harass.interfaces.cli.benchmark_command import (
    RunOptions,
    run_benchmark_command,
)

ENVIRONMENT_FILE = Path(".env")
SERVER_TIMEOUT_SECONDS = 120
FAST_VARIABLE = "HARASS_QWENGUARD_SMALL_URL"
STRONG_VARIABLE = "HARASS_QWENGUARD_URL"


type JudgeFactory = Callable[[httpx.AsyncClient, Rubrics], ResponseJudge]

SERVER_JUDGES: dict[str, tuple[str, JudgeFactory]] = {
    "d1": ("HARASS_D1_URL", D1ResponseJudge),
    "faisal": ("HARASS_FAISAL_URL", FaisalResponseJudge),
    "qwenguard": (
        "HARASS_QWENGUARD_URL",
        lambda client, rubrics: QwenGuardResponseJudge(client),
    ),
    "qwenguard-small": (
        "HARASS_QWENGUARD_SMALL_URL",
        lambda client, rubrics: QwenGuardResponseJudge(client),
    ),
    "shieldstral": (
        "HARASS_SHIELDSTRAL_URL",
        lambda client, rubrics: ShieldstralResponseJudge(client),
    ),
}


type PairFactory = Callable[
    [httpx.AsyncClient, httpx.AsyncClient], ResponseJudge
]

PAIR_JUDGES: dict[str, tuple[tuple[str, str], PairFactory]] = {
    "escalating": (
        (FAST_VARIABLE, STRONG_VARIABLE),
        lambda fast, strong: EscalatingResponseJudge(
            QwenGuardResponseJudge(fast), QwenGuardResponseJudge(strong)
        ),
    ),
    "split": (
        ("HARASS_FAISAL_URL", STRONG_VARIABLE),
        lambda faisal, strong: SplitResponseJudge(
            FaisalResponseJudge(faisal, load_rubrics(RUBRIC_DIRECTORY)),
            QwenGuardResponseJudge(strong),
        ),
    ),
}


async def _run(cases: list[GoldCase], options: RunOptions) -> dict[str, Any]:
    """Judge the cases with the selected judge and report agreement."""
    load_dotenv(ENVIRONMENT_FILE)
    if options.judge in PAIR_JUDGES:
        variables, build_pair = PAIR_JUDGES[options.judge]
        return await _run_pair(cases, options, variables, build_pair)
    address_variable, build_judge_for = SERVER_JUDGES[options.judge]
    return await _run_on_server(
        cases, options, address_variable, build_judge_for
    )


def _server_address(address_variable: str) -> str:
    """Read the address of a decision server from the environment."""
    address = os.environ.get(address_variable, "").strip()
    if not address:
        raise SettingsError(
            f"Environment variable {address_variable} is required; "
            "see .env.example."
        )
    return address


async def _server_health(
    client: httpx.AsyncClient, address_variable: str
) -> dict[str, Any]:
    """Return the identity a decision server reports about itself."""
    try:
        health: dict[str, Any] = (
            (await client.get("/health")).raise_for_status().json()
        )
    except httpx.HTTPError as error:
        raise ConnectionError(
            f"The server at {address_variable} did not answer its "
            "health check."
        ) from error
    return health


async def _run_on_server(
    cases: list[GoldCase],
    options: RunOptions,
    address_variable: str,
    build_judge_for: JudgeFactory,
) -> dict[str, Any]:
    """Judge the cases with a decision model served by the judge host."""
    async with httpx.AsyncClient(
        base_url=_server_address(address_variable),
        timeout=SERVER_TIMEOUT_SECONDS,
    ) as client:
        health = await _server_health(client, address_variable)
        judge = build_judge_for(client, load_rubrics(RUBRIC_DIRECTORY))
        results = await run_benchmark(cases, judge, options.trials)
    description = {
        "model": health["model"],
        "revision": health["revision"],
        "quantization": options.quantization or health["dtype"],
        "rubric_fingerprint": rubric_fingerprint(),
    }
    return benchmark_report(results, judge=description, split=options.split)


async def _run_pair(
    cases: list[GoldCase],
    options: RunOptions,
    variables: tuple[str, str],
    build_pair: Callable[
        [httpx.AsyncClient, httpx.AsyncClient], ResponseJudge
    ],
) -> dict[str, Any]:
    """Judge with two decision servers combined by one composite judge."""
    async with (
        httpx.AsyncClient(
            base_url=_server_address(variables[0]),
            timeout=SERVER_TIMEOUT_SECONDS,
        ) as first,
        httpx.AsyncClient(
            base_url=_server_address(variables[1]),
            timeout=SERVER_TIMEOUT_SECONDS,
        ) as second,
    ):
        healths = [
            await _server_health(first, variables[0]),
            await _server_health(second, variables[1]),
        ]
        results = await run_benchmark(
            cases, build_pair(first, second), options.trials
        )
    description = {
        "model": " then ".join(health["model"] for health in healths),
        "revision": " then ".join(health["revision"] for health in healths),
        "quantization": " then ".join(health["dtype"] for health in healths),
        "rubric_fingerprint": rubric_fingerprint(),
    }
    return benchmark_report(results, judge=description, split=options.split)


def _publish(report_file: Path) -> str:
    """Store a report file in the database for the administrator pages."""
    load_dotenv(ENVIRONMENT_FILE)
    backend = BackendSettings.from_environment(os.environ)
    document = json.loads(report_file.read_text(encoding="utf-8"))
    engine = create_engine(
        backend.database_url,
        connect_args={"connect_timeout": 10},
        pool_pre_ping=True,
    )
    try:
        require_current_schema(engine)
        reports = JudgeBenchmarkReports(
            SqlAlchemyJudgeBenchmarkStore(sessionmaker(engine))
        )
        return reports.publish(document)
    finally:
        engine.dispose()


async def _main_async(argv: list[str]) -> int:
    """Run the command and report missing configuration."""
    try:
        return await run_benchmark_command(
            argv,
            load_gold_cases,
            _run,
            write_annotation_sheet,
            _publish,
            sys.stdout,
        )
    except SettingsError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


def main() -> None:
    """Entry point of the ``harass-judge-benchmark`` command."""
    sys.exit(asyncio.run(_main_async(sys.argv[1:])))


if __name__ == "__main__":
    main()
