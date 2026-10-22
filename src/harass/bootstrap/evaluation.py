"""Shared execution assembly and immutable worker configuration fingerprints."""

import hashlib
from functools import partial
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING

from harass.application.use_cases.run_evaluation import RunEvaluation
from harass.infrastructure.dataset.spreadsheet_seed_source import SpreadsheetSeedSource
from harass.infrastructure.dataset.yaml_variant_catalog import YamlVariantCatalog
from harass.infrastructure.http.endpoint_policy import EndpointPolicy
from harass.infrastructure.pyrit.scoring.jev_scorer import JevJudge
from harass.infrastructure.settings import Settings

if TYPE_CHECKING:
    from pyrit.prompt_target import PromptTarget

DATASET_FILE = Path("data/test_dataset.xlsx")
TEMPLATES_DIR = Path("config/templates")


def execution_profile(settings: Settings) -> str:
    """Hash actual execution inputs without persisting model credentials."""
    digest = hashlib.sha256(repr(settings).encode("utf-8"))
    for dependency in ("pyrit", "openai", "httpx", "sqlalchemy"):
        digest.update(f"{dependency}:{version(dependency)}".encode())
    package = Path(__file__).resolve().parents[1]
    sources = [
        DATASET_FILE,
        package / "domain/metrics.py",
        package / "domain/case_outcome.py",
        package / "application/evaluation_report.py",
        package / "application/report_document.py",
        package / "application/outcome_codec.py",
        package / "application/use_cases/run_evaluation.py",
        package / "bootstrap/evaluation.py",
        package / "application/variant_evaluation_engine.py",
        package / "domain/adaptive_controller.py",
        package / "domain/owasp_scenario.py",
        package / "infrastructure/dataset/prompt_transforms.py",
        package / "infrastructure/pyrit/variant_attempt_executor.py",
        package / "infrastructure/pyrit/target_builder.py",
        package / "infrastructure/pyrit/judge_request_audit.py",
        package / "infrastructure/settings.py",
        package / "infrastructure/http/endpoint_policy.py",
        package / "infrastructure/dataset/spreadsheet_seed_source.py",
        *sorted(TEMPLATES_DIR.glob("*.yaml")),
        *sorted((package / "infrastructure/pyrit/scoring").rglob("*.py")),
        *sorted((package / "infrastructure/pyrit/scoring/rubrics").glob("*.yaml")),
    ]
    for source in sources:
        digest.update(source.name.encode("utf-8"))
        with source.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def build_evaluation(
    settings: Settings,
    dataset_file: Path = DATASET_FILE,
    templates_directory: Path = TEMPLATES_DIR,
) -> tuple[RunEvaluation, "PromptTarget | JevJudge"]:
    """Build model resources only in an evaluation process, not the HTTP application."""
    from harass.application.variant_evaluation_engine import VariantEvaluationEngine
    from harass.infrastructure.pyrit.scoring.scorer_builder import (
        build_attack_success_scorer,
        build_response_category_scorer,
    )
    from harass.infrastructure.pyrit.target_builder import build_judge, build_target
    from harass.infrastructure.pyrit.variant_attempt_executor import PyritAttemptExecutor

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
                build_response_category_scorer(judge),
                build_attack_success_scorer(judge),
                attempt_timeout_seconds=settings.attempt_timeout_seconds,
            ),
        ),
        execution_settings={
            "target_generation": {
                "temperature": settings.target_generation.temperature,
                "max_completion_tokens": (
                    settings.target_generation.max_completion_tokens
                ),
            },
            "judge": {
                "provider": "typesafe",
                "model": settings.judge.model_name,
                "min_confidence": settings.judge.min_confidence,
            },
            "attempt_timeout_seconds": settings.attempt_timeout_seconds,
            "dataset_sha256": hashlib.sha256(
                dataset_file.read_bytes()
            ).hexdigest(),
            "dependencies": {
                name: version(name)
                for name in ("pyrit", "openai", "httpx", "sqlalchemy")
            },
        },
    )
    return evaluation, judge