"""Compose evaluation dependencies and configuration fingerprints."""

from functools import partial
from pathlib import Path

import httpx

from harass.application.evaluation.runner import RunEvaluation
from harass.infrastructure.dataset.spreadsheet_seed_source import (
    SpreadsheetSeedSource,
)
from harass.infrastructure.dataset.yaml_variant_catalog import (
    YamlVariantCatalog,
)
from harass.infrastructure.http.endpoint_policy import EndpointPolicy
from harass.infrastructure.settings import Settings

DATASET_FILE = Path("data/test_dataset.xlsx")
TEMPLATES_DIR = Path("config/templates")
JUDGE_TIMEOUT_SECONDS = 120


def build_evaluation(
    settings: Settings,
    dataset_file: Path = DATASET_FILE,
    templates_directory: Path = TEMPLATES_DIR,
) -> tuple[RunEvaluation, httpx.AsyncClient]:
    """Build model resources for an evaluation process.

    The returned client talks to the judge server and belongs to the caller,
    which closes it when the process ends.
    """
    from harass.application.evaluation.variant_engine import (
        VariantEvaluationEngine,
    )
    from harass.infrastructure.pyrit.judge_request_audit import audited_client
    from harass.infrastructure.pyrit.scoring.guard_scorers import (
        GuardAttackScorer,
        GuardCategoryScorer,
        GuardModerator,
    )
    from harass.infrastructure.pyrit.target_builder import build_target
    from harass.infrastructure.pyrit.variant_attempt_executor import (
        PyritAttemptExecutor,
    )

    judge = audited_client(settings.judge_server_url, JUDGE_TIMEOUT_SECONDS)
    moderator = GuardModerator(judge)
    evaluation = RunEvaluation(
        SpreadsheetSeedSource(dataset_file),
        VariantEvaluationEngine(
            YamlVariantCatalog(templates_directory),
            PyritAttemptExecutor(
                partial(
                    build_target,
                    generation=settings.target_generation,
                    endpoint_policy=EndpointPolicy(
                        settings.target_private_hosts,
                        settings.target_allow_http,
                    ),
                ),
                GuardCategoryScorer(moderator=moderator),
                GuardAttackScorer(moderator=moderator),
                attempt_timeout_seconds=settings.attempt_timeout_seconds,
            ),
        ),
    )
    return evaluation, judge
