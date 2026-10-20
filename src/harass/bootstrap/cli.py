"""Composition root of the command-line interface."""

import asyncio
import logging
import os
import sys
from functools import partial
from pathlib import Path

from dotenv import load_dotenv
from pyrit.prompt_target import PromptTarget
from pyrit.setup import SQLITE, initialize_pyrit_async

from harass.application.use_cases.run_evaluation import RunEvaluation
from harass.application.variant_evaluation_engine import VariantEvaluationEngine
from harass.infrastructure.dataset.spreadsheet_seed_source import SpreadsheetSeedSource
from harass.infrastructure.dataset.yaml_variant_catalog import YamlVariantCatalog
from harass.infrastructure.http.endpoint_policy import EndpointPolicy
from harass.infrastructure.pyrit.scoring.jev_scorer import JevJudge
from harass.infrastructure.pyrit.scoring.scorer_builder import (
    build_attack_success_scorer,
    build_response_category_scorer,
)
from harass.infrastructure.pyrit.target_builder import build_judge, build_target, close_target
from harass.infrastructure.pyrit.variant_attempt_executor import PyritAttemptExecutor
from harass.infrastructure.reporting.json_report_exporter import JsonReportExporter
from harass.infrastructure.settings import Settings, SettingsError
from harass.interfaces.cli.evaluate_command import (
    EvaluateCommand,
    parse_command,
    run_evaluate_command,
)

ENVIRONMENT_FILE = Path(".env")


def _use_case_factory(
    settings: Settings, resources: list[PromptTarget | JevJudge], command: EvaluateCommand
) -> RunEvaluation:
    """Wire the use case to the PyRIT adapters for the files named on the command line."""
    catalog = YamlVariantCatalog(Path(command.arguments.templates_directory))
    judge = build_judge(settings.judge)
    resources.append(judge)
    engine = VariantEvaluationEngine(
        catalog,
        PyritAttemptExecutor(
            partial(
                build_target,
                generation=settings.target_generation,
                endpoint_policy=EndpointPolicy(
                    settings.target_private_hosts, settings.target_allow_http
                ),
            ),
            build_response_category_scorer(judge),
            build_attack_success_scorer(judge),
            attempt_timeout_seconds=settings.attempt_timeout_seconds,
        ),
    )
    return RunEvaluation(
        seed_source=SpreadsheetSeedSource(command.dataset_file),
        engine=engine,
    )


async def _main_async(argv: list[str]) -> int:
    """Parse the command, load settings, initialize persistent PyRIT memory and run."""
    command = parse_command(argv)
    load_dotenv(ENVIRONMENT_FILE)
    try:
        settings = Settings.from_environment(os.environ)
    except SettingsError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    # PyRIT stores every prompt, response and score in its SQLite database, so a run can be
    # inspected after the fact; its default techniques and targets are not needed here.
    # The run seed also seeds PyRIT's random streams, so any stochastic transform is reproducible.
    await initialize_pyrit_async(
        memory_db_type=SQLITE,
        load_defaults=False,
        silent=True,
        seed=command.arguments.sampling_seed,
    )
    resources: list[PromptTarget | JevJudge] = []
    try:
        return await run_evaluate_command(
            command,
            os.environ,
            partial(_use_case_factory, settings, resources),
            JsonReportExporter(),
            sys.stdout,
        )
    finally:
        for target in resources:
            await close_target(target)


def main() -> None:
    """Entry point of the ``harass`` command."""
    logging.basicConfig(
        level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("harass").setLevel(logging.INFO)
    sys.exit(asyncio.run(_main_async(sys.argv[1:])))
