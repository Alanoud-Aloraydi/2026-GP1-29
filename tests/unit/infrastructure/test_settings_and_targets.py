"""Tests for system settings and the construction of PyRIT targets."""

import pytest

from harass.domain.target_connection import TargetConnection
from harass.infrastructure.pyrit.target_builder import (
    build_target,
    close_target,
)
from harass.infrastructure.settings import (
    DEFAULT_TARGET_MAX_COMPLETION_TOKENS,
    DEFAULT_TARGET_TEMPERATURE,
    Settings,
    SettingsError,
    TargetGenerationSettings,
)

REQUIRED_ENVIRONMENT = {"HARASS_JUDGE_SERVER_URL": "http://judge-host:8083"}
CONNECTION = TargetConnection(
    base_url="https://api.example.com/v1", model_name="model", api_key="k"
)


def test_optional_settings_fall_back_to_documented_defaults() -> None:
    """Only the judge server address is mandatory."""
    settings = Settings.from_environment(REQUIRED_ENVIRONMENT)

    assert settings.judge_server_url == "http://judge-host:8083"
    assert settings.target_generation.temperature == DEFAULT_TARGET_TEMPERATURE
    assert (
        settings.target_generation.max_completion_tokens
        == DEFAULT_TARGET_MAX_COMPLETION_TOKENS
    )


def test_missing_required_setting_names_the_variable() -> None:
    """The error tells the operator exactly which variable to set."""
    with pytest.raises(SettingsError, match="HARASS_JUDGE_SERVER_URL"):
        Settings.from_environment({"HARASS_JUDGE_SERVER_URL": " "})


def test_malformed_number_is_rejected() -> None:
    """Numeric settings are validated instead of failing later inside a run."""
    environment = {
        **REQUIRED_ENVIRONMENT,
        "HARASS_TARGET_TEMPERATURE": "cold",
    }

    with pytest.raises(SettingsError, match="HARASS_TARGET_TEMPERATURE"):
        Settings.from_environment(environment)


@pytest.mark.parametrize("raw_value", ["0", "-5", "12.5", "many"])
def test_token_limits_must_be_positive_whole_numbers(raw_value: str) -> None:
    """Verify token limits must be positive whole numbers."""
    environment = {
        **REQUIRED_ENVIRONMENT,
        "HARASS_TARGET_MAX_COMPLETION_TOKENS": raw_value,
    }

    with pytest.raises(
        SettingsError, match="HARASS_TARGET_MAX_COMPLETION_TOKENS"
    ):
        Settings.from_environment(environment)


def test_malformed_boolean_is_rejected() -> None:
    """True/false settings accept only true or false."""
    environment = {**REQUIRED_ENVIRONMENT, "HARASS_ALLOW_TARGET_HTTP": "yes"}

    with pytest.raises(SettingsError, match="HARASS_ALLOW_TARGET_HTTP"):
        Settings.from_environment(environment)


@pytest.mark.usefixtures("pyrit_memory")
def test_target_applies_system_wide_generation_settings() -> None:
    """Every model under evaluation receives the same decoding parameters."""
    target = build_target(
        CONNECTION,
        TargetGenerationSettings(temperature=0.0, max_completion_tokens=900),
    )

    parameters = target.get_identifier().params
    assert parameters["temperature"] == 0.0
    assert parameters["max_completion_tokens"] == 900


@pytest.mark.usefixtures("pyrit_memory")
async def test_owned_client_is_closed_before_loop_shutdown() -> None:
    """Verify owned client is closed before loop shutdown."""
    target = build_target(CONNECTION, TargetGenerationSettings())
    assert target._async_client is not None

    await close_target(target)

    assert target._async_client.is_closed()
