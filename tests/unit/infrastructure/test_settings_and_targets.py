"""Tests for system settings and the construction of PyRIT targets."""

import pytest
from pyrit.models import Message

from harass.domain.target_connection import TargetConnection
from harass.infrastructure.pyrit.target_builder import build_judge, build_target, close_target
from harass.infrastructure.settings import (
    DEFAULT_JUDGE_TEMPERATURE,
    DEFAULT_MAX_CONCURRENCY,
    DEFAULT_TARGET_MAX_COMPLETION_TOKENS,
    DEFAULT_TARGET_TEMPERATURE,
    JudgeSettings,
    Settings,
    SettingsError,
    TargetGenerationSettings,
)

REQUIRED_JUDGE_ENVIRONMENT = {
    "HARASS_JUDGE_BASE_URL": "http://localhost:11434/v1",
    "HARASS_JUDGE_MODEL": "judge-model",
    "HARASS_JUDGE_API_KEY": "not-needed",
}


def test_optional_settings_fall_back_to_documented_defaults() -> None:
    """Only the judge endpoint, model and key are mandatory."""
    settings = Settings.from_environment(REQUIRED_JUDGE_ENVIRONMENT)

    assert settings.judge.temperature == DEFAULT_JUDGE_TEMPERATURE
    assert settings.target_generation.temperature == DEFAULT_TARGET_TEMPERATURE
    assert settings.target_generation.max_completion_tokens == DEFAULT_TARGET_MAX_COMPLETION_TOKENS
    assert settings.max_concurrency == DEFAULT_MAX_CONCURRENCY


def test_missing_required_setting_names_the_variable() -> None:
    """The error tells the operator exactly which variable to set."""
    environment = {**REQUIRED_JUDGE_ENVIRONMENT, "HARASS_JUDGE_MODEL": " "}

    with pytest.raises(SettingsError, match="HARASS_JUDGE_MODEL"):
        Settings.from_environment(environment)


def test_malformed_number_is_rejected() -> None:
    """Numeric settings are validated instead of failing later inside a run."""
    environment = {**REQUIRED_JUDGE_ENVIRONMENT, "HARASS_TARGET_TEMPERATURE": "cold"}

    with pytest.raises(SettingsError, match="HARASS_TARGET_TEMPERATURE"):
        Settings.from_environment(environment)


def test_judge_settings_never_expose_the_api_key() -> None:
    """Settings can be logged without leaking the judge key."""
    settings = JudgeSettings(base_url="http://judge/v1", model_name="judge", api_key="secret")

    assert "secret" not in repr(settings)


@pytest.mark.usefixtures("pyrit_memory")
def test_target_applies_system_wide_generation_settings() -> None:
    """Every model under evaluation receives the same decoding parameters."""
    target = build_target(
        TargetConnection(base_url="https://api.example.com/v1", model_name="model", api_key="k"),
        TargetGenerationSettings(temperature=0.0, max_completion_tokens=900),
    )

    parameters = target.get_identifier().params
    assert parameters["temperature"] == 0.0
    assert parameters["max_completion_tokens"] == 900


@pytest.mark.usefixtures("pyrit_memory")
@pytest.mark.parametrize(
    ("supports_system_prompt", "expected_roles"), [(True, ["system", "user"]), (False, ["user"])]
)
async def test_judge_system_prompt_handling_follows_the_setting(
    supports_system_prompt: bool, expected_roles: list[str]
) -> None:
    """Scorer instructions stay a system message or are folded into the user turn as configured."""
    judge = build_judge(
        JudgeSettings(
            base_url="http://localhost:11434/v1",
            model_name="judge",
            api_key="key",
            supports_system_prompt=supports_system_prompt,
        )
    )
    conversation = [
        Message.from_prompt(prompt="scoring instructions", role="system"),
        Message.from_prompt(prompt="response to score", role="user"),
    ]

    normalized = await judge.configuration.normalize_async(messages=conversation)

    assert [message.api_role for message in normalized] == expected_roles
    sent_text = " ".join(message.message_pieces[0].converted_value for message in normalized)
    assert "scoring instructions" in sent_text
    assert "response to score" in sent_text


@pytest.mark.parametrize("raw_value", ["0", "-5", "12.5", "many"])
def test_token_limits_must_be_positive_whole_numbers(raw_value: str) -> None:
    """A token limit of zero, a negative or a fraction cannot bound generation."""
    environment = {**REQUIRED_JUDGE_ENVIRONMENT, "HARASS_JUDGE_MAX_COMPLETION_TOKENS": raw_value}

    with pytest.raises(SettingsError, match="HARASS_JUDGE_MAX_COMPLETION_TOKENS"):
        Settings.from_environment(environment)


@pytest.mark.usefixtures("pyrit_memory")
def test_judge_generation_is_bounded() -> None:
    """Every judge call carries the configured completion limit."""
    judge = build_judge(
        JudgeSettings(
            base_url="http://localhost:11434/v1",
            model_name="judge",
            api_key="key",
            max_completion_tokens=12288,
        )
    )

    assert judge.get_identifier().params["max_completion_tokens"] == 12288


@pytest.mark.usefixtures("pyrit_memory")
async def test_owned_client_is_closed_before_loop_shutdown() -> None:
    """Explicit disposal avoids scheduling network cleanup after the event loop is closed."""
    judge = build_judge(
        JudgeSettings(base_url="http://judge.invalid/v1", model_name="j", api_key="k")
    )
    assert judge._async_client is not None
    await close_target(judge)
    assert judge._async_client.is_closed()


@pytest.mark.usefixtures("pyrit_memory")
async def test_ollama_receives_only_its_supported_token_limit_parameter() -> None:
    """The actual request carries max_tokens rather than an ignored completion limit."""
    from inspect import signature

    from pyrit.models import JsonResponseConfig

    judge = build_judge(
        JudgeSettings(
            base_url="http://judge.invalid/v1",
            model_name="j",
            api_key="k",
            max_completion_tokens=32,
            token_limit_parameter="max_tokens",
            keep_alive="30m",
        )
    )
    try:
        body = await judge._construct_request_body_async(
            conversation=[Message.from_prompt(prompt="hello", role="user")],
            json_config=JsonResponseConfig(enabled=False),
        )
        assert body["max_tokens"] == 32
        assert "max_completion_tokens" not in body
        assert body["extra_body"] == {"keep_alive": "30m"}
        assert "keep_alive" not in body
        assert judge._async_client is not None
        signature(judge._async_client.chat.completions.create).bind(**body)
    finally:
        await close_target(judge)


def test_invalid_judge_token_limit_parameter_fails_early() -> None:
    """An unsupported field cannot silently make generation unbounded."""
    with pytest.raises(SettingsError, match="token limit parameter"):
        JudgeSettings(
            base_url="http://judge/v1",
            model_name="j",
            api_key="k",
            token_limit_parameter="unknown",
        )


def test_malformed_boolean_is_rejected() -> None:
    """True/false settings accept only true or false."""
    environment = {**REQUIRED_JUDGE_ENVIRONMENT, "HARASS_JUDGE_SUPPORTS_SYSTEM_PROMPT": "yes"}

    with pytest.raises(SettingsError, match="HARASS_JUDGE_SUPPORTS_SYSTEM_PROMPT"):
        Settings.from_environment(environment)


@pytest.mark.parametrize("raw_value", ["2", "0"])
def test_judge_votes_must_be_odd_and_positive(raw_value: str) -> None:
    """An even vote count could tie a true/false verdict."""
    environment = {**REQUIRED_JUDGE_ENVIRONMENT, "HARASS_JUDGE_VOTES": raw_value}

    with pytest.raises(SettingsError, match=r"HARASS_JUDGE_VOTES|votes"):
        Settings.from_environment(environment)
