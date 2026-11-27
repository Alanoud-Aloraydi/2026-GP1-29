"""Compose evaluation dependencies and configuration fingerprints."""

from functools import partial
from pathlib import Path

import httpx

from harass.application.evaluation.baseline_engine import BaselineEngine
from harass.application.evaluation.runner import RunEvaluation
from harass.application.ports.evaluation import AttemptExecutor
from harass.infrastructure.dataset.spreadsheet_seed_source import SpreadsheetSeedSource
from harass.infrastructure.http.endpoint_policy import EndpointPolicy
from harass.infrastructure.settings import Settings

DATASET_FILE = Path("data/baseline_dataset.xlsx")
JUDGE_TIMEOUT_SECONDS = 120


def build_attempt_executor(settings: Settings) -> tuple[AttemptExecutor, httpx.AsyncClient]:
    """Build the target and judge tail that executes one scored attempt.

    Evaluation runs and the prompt generator share it, so a generated prompt
    is sent and judged exactly like a dataset prompt. The returned client
    talks to the judge server and belongs to the caller, which closes it.
    """
    # PyRIT loads slowly; importing it here keeps it out of the API process,
    # which reads this module's paths but never runs attempts.
    from harass.infrastructure.pyrit.attempt_executor import PyritAttemptExecutor
    from harass.infrastructure.pyrit.judge_request_audit import audited_client
    from harass.infrastructure.pyrit.scoring.guard_scorers import (
        GuardAttackScorer,
        GuardCategoryScorer,
        GuardModerator,
    )
    from harass.infrastructure.pyrit.target_builder import build_target

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


def build_evaluation(executor: AttemptExecutor, dataset_file: Path = DATASET_FILE) -> RunEvaluation:
    """Build the baseline evaluation over the dataset on a shared attempt executor."""
    return RunEvaluation(SpreadsheetSeedSource(dataset_file), BaselineEngine(executor))
