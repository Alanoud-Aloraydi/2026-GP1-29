"""Jev-only settings and unchanged target generation."""

import pytest

from harass.domain.target_connection import TargetConnection
from harass.infrastructure.pyrit.scoring.jev_scorer import JevJudge
from harass.infrastructure.pyrit.target_builder import build_judge, build_target, close_target
from harass.infrastructure.settings import (
    JudgeSettings,
    Settings,
    SettingsError,
    TargetGenerationSettings,
)


def test_only_typesafe_key_is_required() -> None:
    """Default settings use Jev without requiring any old endpoint."""
    settings = Settings.from_environment({"TYPESAFE_API_KEY": "secret"})
    assert settings.judge.model_name == "jev-1.13.0"
    assert settings.judge.min_confidence == 0.8
    assert "secret" not in repr(settings)


def test_old_judge_environment_does_not_enable_a_chat_judge() -> None:
    """A legacy credential cannot accidentally reactivate the removed path."""
    with pytest.raises(SettingsError, match="TYPESAFE_API_KEY"):
        Settings.from_environment({"HARASS_JUDGE_API_KEY": "old-key"})


@pytest.mark.parametrize("value", ["nan", "inf", "-0.1", "1.1", "bad"])
def test_invalid_review_threshold_is_rejected(value: str) -> None:
    """Invalid thresholds fail before any provider request."""
    with pytest.raises(SettingsError):
        Settings.from_environment({"TYPESAFE_API_KEY": "k", "HARASS_JEV_MIN_CONFIDENCE": value})


async def test_judge_always_is_jev_and_closes() -> None:
    """Construct and close the only supported model judge."""
    judge = build_judge(JudgeSettings(api_key="secret"))
    assert isinstance(judge, JevJudge)
    await close_target(judge)
    assert judge.client.is_closed


@pytest.mark.usefixtures("pyrit_memory")
async def test_target_generation_is_unchanged() -> None:
    """Target decoding stays independent of the judging replacement."""
    target = build_target(
        TargetConnection("https://example.com/v1", "target", "k"), TargetGenerationSettings()
    )
    assert target.get_identifier().params["temperature"] == 0.0
    assert target.get_identifier().params["max_completion_tokens"] == 900
    await close_target(target)
