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

from harass.application.evaluation.runner import RunEvaluation
from harass.bootstrap.evaluation import build_evaluation
from harass.infrastructure.pyrit.target_builder import close_target
from harass.infrastructure.reporting.json_report_exporter import (
    JsonReportExporter,
)
from harass.infrastructure.settings import Settings, SettingsError
from harass.interfaces.cli.evaluate_command import (
    EvaluateCommand,
    parse_command,
    run_evaluate_command,
)

ENVIRONMENT_FILE = Path(".env")


def _use_case_factory(
    settings: Settings, resources: list[PromptTarget], command: EvaluateCommand
) -> RunEvaluation:
    """Build CLI evaluation dependencies from the selected input files."""
    evaluation, judge = build_evaluation(
        settings,
        command.dataset_file,
        Path(command.arguments.templates_directory),
    )
    resources.append(judge)
    return evaluation


async def _main_async(argv: list[str]) -> int:
    """Load CLI settings and execute the configured evaluation."""
    command = parse_command(argv)
    load_dotenv(ENVIRONMENT_FILE)
    try:
        settings = Settings.from_environment(os.environ)
    except SettingsError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    # Retain PyRIT evidence in SQLite and seed its random transformations.
    await initialize_pyrit_async(
        memory_db_type=SQLITE,
        load_defaults=False,
        silent=True,
        seed=command.arguments.sampling_seed,
    )
    resources: list[PromptTarget] = []
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
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("harass").setLevel(logging.INFO)
    sys.exit(asyncio.run(_main_async(sys.argv[1:])))
