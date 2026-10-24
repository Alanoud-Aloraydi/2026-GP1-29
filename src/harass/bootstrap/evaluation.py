"""Compose evaluation dependencies and configuration fingerprints."""

from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from harass.application.evaluation.runner import RunEvaluation
from harass.infrastructure.dataset.spreadsheet_seed_source import (
    SpreadsheetSeedSource,
)
from harass.infrastructure.dataset.yaml_variant_catalog import (
    YamlVariantCatalog,
)
from harass.infrastructure.http.endpoint_policy import EndpointPolicy
from harass.infrastructure.settings import Settings

if TYPE_CHECKING:
    from pyrit.prompt_target import PromptTarget

DATASET_FILE = Path("data/test_dataset.xlsx")
TEMPLATES_DIR = Path("config/templates")


def build_evaluation(
    settings: Settings,
    dataset_file: Path = DATASET_FILE,
    templates_directory: Path = TEMPLATES_DIR,
) -> tuple[RunEvaluation, "PromptTarget"]:
    """Build model resources for an evaluation process."""
    from harass.application.evaluation.variant_engine import (
        VariantEvaluationEngine,
    )
    from harass.infrastructure.pyrit.scoring.scorer_builder import (
        build_attack_success_scorer,
        build_response_category_scorer,
    )
    from harass.infrastructure.pyrit.target_builder import (
        build_judge,
        build_target,
    )
    from harass.infrastructure.pyrit.variant_attempt_executor import (
        PyritAttemptExecutor,
    )

    judge = build_judge(settings.judge)
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
                build_response_category_scorer(
                    judge,
                    votes=settings.judge.votes,
                    structured_output=settings.judge.supports_json_output,
                ),
                build_attack_success_scorer(
                    judge,
                    votes=settings.judge.votes,
                    structured_output=settings.judge.supports_json_output,
                ),
                attempt_timeout_seconds=settings.attempt_timeout_seconds,
            ),
        ),
    )
    return evaluation, judge
