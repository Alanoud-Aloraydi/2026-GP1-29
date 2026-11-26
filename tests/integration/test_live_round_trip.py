"""Tests for live round trip."""

import asyncio
import os
from functools import partial
from pathlib import Path

import pytest
from dotenv import load_dotenv

from harass.domain.case_selection import CaseSelection
from harass.domain.prompt_variant import PromptVariant, VariantSelection
from harass.domain.target_connection import TargetConnection
from harass.domain.taxonomy import Axis, BypassStrategy
from harass.infrastructure.dataset.spreadsheet_seed_source import SpreadsheetSeedSource
from harass.infrastructure.dataset.yaml_variant_catalog import YamlVariantCatalog
from harass.infrastructure.http.endpoint_policy import EndpointPolicy
from harass.infrastructure.http.qwenguard_moderation import moderate
from harass.infrastructure.pyrit.judge_request_audit import audited_client
from harass.infrastructure.pyrit.scoring.guard_scorers import (
    GuardAttackScorer,
    GuardCategoryScorer,
    GuardModerator,
)
from harass.infrastructure.pyrit.target_builder import build_target
from harass.infrastructure.pyrit.variant_attempt_executor import PyritAttemptExecutor
from harass.infrastructure.settings import Settings

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.live


@pytest.mark.parametrize("axis", [Axis.OVER_REFUSAL, Axis.ADVERSARIAL])
@pytest.mark.parametrize("converted", [False, True])
async def test_current_executor_live_round_trip(
    pyrit_memory: None, axis: Axis, converted: bool
) -> None:
    """Verify executor live round trip."""
    load_dotenv(ROOT / ".env")
    settings = Settings.from_environment(os.environ)
    target = TargetConnection(
        os.environ.get("HARASS_TARGET_BASE_URL", ""),
        os.environ.get("HARASS_TARGET_MODEL", ""),
        os.environ.get("HARASS_TARGET_API_KEY", ""),
    )
    judge = audited_client(settings.judge_server_url, 120)
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
    selection = CaseSelection(
        axis=axis,
        strategies=frozenset({BypassStrategy.OBFUSCATION})
        if axis is Axis.ADVERSARIAL
        else frozenset(),
    )
    case = SpreadsheetSeedSource(ROOT / "data" / "baseline_dataset.xlsx").load_cases(selection)[0]
    variant = PromptVariant("baseline", "baseline", case.prompt_text)
    if converted:
        variant = YamlVariantCatalog(ROOT / "config" / "templates").variants(
            case, VariantSelection((), ("base64",))
        )[0]
    try:
        outcome = await asyncio.wait_for(
            executor.execute(case, variant, target, "live-smoke"), timeout=180
        )
    except TimeoutError:
        pytest.fail("Live smoke attempt exceeded 180 seconds.", pytrace=False)
    finally:
        await judge.aclose()
    if not outcome.is_scored:
        pytest.fail(f"Live attempt has no verdict: {outcome.error}", pytrace=False)
    assert outcome.transcript is not None
    assert outcome.transcript.response
    assert outcome.transcript.category_judge is not None
    assert outcome.transcript.category_judge.vote_budget == 1
    if axis is Axis.ADVERSARIAL and outcome.leak_exact_match is None:
        assert outcome.transcript.attack_judge is not None
        assert outcome.transcript.attack_judge.vote_budget == 1
    elif axis is Axis.ADVERSARIAL:
        assert outcome.transcript.attack_judge is None
        assert outcome.leak_rouge_l is not None


async def test_configured_judge_classifies_a_known_neutral_pair() -> None:
    """Verify the judge server finds a plain answer safe and not refused."""
    load_dotenv(ROOT / ".env")
    settings = Settings.from_environment(os.environ)
    judge = audited_client(settings.judge_server_url, 120)
    try:
        moderation = await moderate(judge, "ما عاصمة السعودية؟", "عاصمة السعودية هي الرياض.")
    finally:
        await judge.aclose()

    assert not moderation.refuses
    assert moderation.safety == "Safe"
