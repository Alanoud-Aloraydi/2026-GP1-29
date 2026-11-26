"""Compose evaluation dependencies and configuration fingerprints."""

from functools import partial
from pathlib import Path

import httpx

from harass.application.evaluation.runner import RunEvaluation
from harass.application.ports.evaluation import AttemptExecutor
from harass.infrastructure.dataset.spreadsheet_seed_source import SpreadsheetSeedSource
from harass.infrastructure.dataset.yaml_variant_catalog import YamlVariantCatalog
from harass.infrastructure.http.endpoint_policy import EndpointPolicy
from harass.infrastructure.settings import Settings

DATASET_FILE = Path("data/baseline_dataset.xlsx")
TEMPLATES_DIR = Path("config/templates")
JUDGE_TIMEOUT_SECONDS = 120


def build_attempt_executor(settings: Settings) -> tuple[AttemptExecutor, httpx.AsyncClient]:
    """Build the target and judge tail that executes one scored attempt.

    Evaluation runs and the prompt generator share it, so a generated prompt
    is sent and judged exactly like a dataset prompt. The returned client
    talks to the judge server and belongs to the caller, which closes it.
    """
    # PyRIT loads slowly; importing it here keeps it out of the API process,
    # which reads this module's paths but never runs attempts.
    from harass.infrastructure.pyrit.judge_request_audit import audited_client
    from harass.infrastructure.pyrit.scoring.guard_scorers import (
        GuardAttackScorer,
        GuardCategoryScorer,
        GuardModerator,
    )
    from harass.infrastructure.pyrit.target_builder import build_target
    from harass.infrastructure.pyrit.variant_attempt_executor import PyritAttemptExecutor

    judge = audited_client(settings.judge_server_url, JUDGE_TIMEOUT_SECONDS)
    moderator = GuardModerator(judge)
    executor = PyritAttemptExecutor(
        partial(
            build_target,
            generation=settings.target_generation,
            endpoint_policy=EndpointPolicy(
                settings.target_private_hosts, settings.target_allow_http
            ),
        ),
        GuardCategoryScorer(moderator=moderator),
        GuardAttackScorer(moderator=moderator),
        attempt_timeout_seconds=settings.attempt_timeout_seconds,
    )
    return executor, judge


def build_evaluation(
    settings: Settings, dataset_file: Path = DATASET_FILE, templates_directory: Path = TEMPLATES_DIR
) -> tuple[RunEvaluation, httpx.AsyncClient]:
    """Build model resources for an evaluation process.

    The returned client talks to the judge server and belongs to the caller,
    which closes it when the process ends.
    """
    from harass.application.evaluation.variant_engine import VariantEvaluationEngine

    executor, judge = build_attempt_executor(settings)
    evaluation = RunEvaluation(
        SpreadsheetSeedSource(dataset_file),
        VariantEvaluationEngine(YamlVariantCatalog(templates_directory), executor),
    )
    return evaluation, judge
