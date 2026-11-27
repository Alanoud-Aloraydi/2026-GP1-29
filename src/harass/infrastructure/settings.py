"""System settings read from environment variables."""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

# Fixed greedy decoding follows HarmBench and makes target runs reproducible.
# Arabic commonly needs more tokens per word, so the budget exceeds 512 tokens.
DEFAULT_TARGET_TEMPERATURE = 0.0
DEFAULT_TARGET_MAX_COMPLETION_TOKENS = 900
DEFAULT_ATTEMPT_TIMEOUT_SECONDS = 300


class SettingsError(ValueError):
    """Raised when a required setting is missing or malformed."""


@dataclass(frozen=True)
class TargetGenerationSettings:
    """Apply consistent generation settings to evaluated models."""

    temperature: float = DEFAULT_TARGET_TEMPERATURE
    max_completion_tokens: int = DEFAULT_TARGET_MAX_COMPLETION_TOKENS


@dataclass(frozen=True)
class BackendSettings:
    """Settings the HTTP backend needs beyond the evaluation settings.

    The encryption key protects clients' stored API keys; it is a URL-safe
    base64 Fernet key. The database URL points at the project's PostgreSQL
    instance.
    """

    database_url: str
    encryption_key: str = field(repr=False)
    jwt_secret: str = field(default="", repr=False)
    secure_cookie: bool = True
    session_seconds: int = 900
    refresh_seconds: int = 28800
    previous_jwt_secrets: tuple[str, ...] = field(default=(), repr=False)
    account_email_enabled: bool = False

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "BackendSettings":
        """Build backend settings from ``HARASS_*`` environment variables."""
        return cls(
            database_url=_required(environment, "HARASS_DATABASE_URL"),
            account_email_enabled=_boolean(
                environment, "HARASS_ACCOUNT_EMAIL_ENABLED", default=False
            ),
            encryption_key=_required(environment, "HARASS_ENCRYPTION_KEY"),
            jwt_secret=_required(environment, "HARASS_JWT_SECRET"),
            secure_cookie=_boolean(environment, "HARASS_COOKIE_SECURE", default=True),
            session_seconds=_positive_integer(environment, "HARASS_SESSION_SECONDS", 900),
            refresh_seconds=_positive_integer(environment, "HARASS_REFRESH_SECONDS", 28800),
            previous_jwt_secrets=_list(environment, "HARASS_JWT_PREVIOUS_SECRETS"),
        )


@dataclass(frozen=True)
class Settings:
    """All system-level settings."""

    judge_server_url: str
    target_generation: TargetGenerationSettings
    attempt_timeout_seconds: int = DEFAULT_ATTEMPT_TIMEOUT_SECONDS
    target_private_hosts: tuple[str, ...] = ()
    target_allow_http: bool = False

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "Settings":
        """Build settings from ``HARASS_*`` environment variables."""
        return cls(
            judge_server_url=_required(environment, "HARASS_JUDGE_SERVER_URL"),
            attempt_timeout_seconds=_positive_integer(
                environment, "HARASS_ATTEMPT_TIMEOUT_SECONDS", DEFAULT_ATTEMPT_TIMEOUT_SECONDS
            ),
            target_private_hosts=tuple(
                host.lower() for host in _list(environment, "HARASS_PRIVATE_TARGET_HOSTS")
            ),
            target_allow_http=_boolean(environment, "HARASS_ALLOW_TARGET_HTTP", default=False),
            target_generation=TargetGenerationSettings(
                temperature=_temperature(
                    environment, "HARASS_TARGET_TEMPERATURE", DEFAULT_TARGET_TEMPERATURE
                ),
                max_completion_tokens=_positive_integer(
                    environment,
                    "HARASS_TARGET_MAX_COMPLETION_TOKENS",
                    DEFAULT_TARGET_MAX_COMPLETION_TOKENS,
                ),
            ),
        )


# The generator's own models, verified for this project: Gemma-3-27B leads on
# Arabic idiom (Jais 2 tables, arXiv 2608.13580) and writes the prompts,
# gpt-oss-20b follows the review rubric best, and qwen3.8-27b matched the
# reference safety labels on all 54 calibration items.
DEFAULT_GENERATOR_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_WRITER_MODEL = "google/gemma-3-27b-it"
DEFAULT_REVIEWER_MODEL = "openai/gpt-oss-20b"
DEFAULT_SAFETY_JUDGE_MODEL = "qwen/qwen3.8-27b"
# The attack writer must draft attacks without refusing them; this model wrote
# 30 of 30 in the attacker bake-off. It also localizes attacks, which an
# aligned localizer may refuse to rewrite.
DEFAULT_ATTACKER_ENDPOINT = "https://api.venice.ai/api/v1/chat/completions"
DEFAULT_ATTACKER_MODEL = "deepseek-v4-1-flash-1017-uncensored"


@dataclass(frozen=True)
class GenerationModel:
    """Where one of the generator's own models is reached and under which name."""

    endpoint: str
    api_key: str = field(repr=False)
    model: str


@dataclass(frozen=True)
class GenerationSettings:
    """The models the prompt generator writes and judges with.

    The reviewer and the safety judge belong to other model families than the
    writer, so no model reviews its own writing; the localizer stays in the
    writer's family, which rewrote Arabic varieties best in the bake-off. The
    attacker writes and localizes attacks, and is absent when not configured.
    """

    writer: GenerationModel
    localizer: GenerationModel
    reviewer: GenerationModel
    safety_judge: GenerationModel
    attacker: GenerationModel | None = None

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "GenerationSettings":
        """Build the generator's model settings from the environment."""
        endpoint = (
            environment.get("HARASS_GENERATOR_ENDPOINT", "").strip() or DEFAULT_GENERATOR_ENDPOINT
        )
        api_key = _required(environment, "HARASS_GENERATOR_API_KEY")
        writer = _generation_model(environment, "HARASS_WRITER_MODEL", DEFAULT_WRITER_MODEL)
        return cls(
            writer=GenerationModel(endpoint, api_key, writer),
            localizer=GenerationModel(
                endpoint, api_key, _generation_model(environment, "HARASS_LOCALIZER_MODEL", writer)
            ),
            reviewer=GenerationModel(
                endpoint,
                api_key,
                _generation_model(environment, "HARASS_REVIEWER_MODEL", DEFAULT_REVIEWER_MODEL),
            ),
            safety_judge=GenerationModel(
                endpoint,
                api_key,
                _generation_model(
                    environment, "HARASS_SAFETY_JUDGE_MODEL", DEFAULT_SAFETY_JUDGE_MODEL
                ),
            ),
            attacker=_attacker(environment),
        )


def _attacker(environment: Mapping[str, str]) -> GenerationModel | None:
    """Read the attack writer, or None when no attacker key is configured.

    Over-refusal rounds need no attacker, so its key is optional; an attack
    round without it fails before any model is called.
    """
    api_key = environment.get("HARASS_ATTACKER_API_KEY", "").strip()
    if not api_key:
        return None
    endpoint = environment.get("HARASS_ATTACKER_ENDPOINT", "").strip() or DEFAULT_ATTACKER_ENDPOINT
    model = _generation_model(environment, "HARASS_ATTACKER_MODEL", DEFAULT_ATTACKER_MODEL)
    return GenerationModel(endpoint, api_key, model)


def _generation_model(environment: Mapping[str, str], name: str, default: str) -> str:
    """Read one model name, falling back to the calibrated default."""
    return environment.get(name, "").strip() or default


def _list(environment: Mapping[str, str], name: str) -> tuple[str, ...]:
    """Read a comma-separated setting, dropping blank entries."""
    return tuple(value.strip() for value in environment.get(name, "").split(",") if value.strip())


def _required(environment: Mapping[str, str], name: str) -> str:
    """Return a non-blank variable or explain which one is missing."""
    value = environment.get(name, "").strip()
    if not value:
        raise SettingsError(f"Environment variable {name} is required; see .env.example.")
    return value


def _temperature(environment: Mapping[str, str], name: str, default: float) -> float:
    """Read a sampling temperature between zero and two."""
    raw_value = environment.get(name, "").strip()
    if not raw_value:
        return default
    try:
        value = float(raw_value)
        if not math.isfinite(value) or not 0 <= value <= 2:
            raise ValueError("Temperature must be finite and between zero and two.")
        return value
    except ValueError as error:
        raise SettingsError(
            f"Environment variable {name} must be a number, got '{raw_value}'."
        ) from error


def _boolean(environment: Mapping[str, str], name: str, *, default: bool) -> bool:
    """Read a boolean environment setting."""
    raw_value = environment.get(name, "").strip().lower()
    if not raw_value:
        return default
    if raw_value not in {"true", "false"}:
        raise SettingsError(
            f"Environment variable {name} must be true or false, got '{raw_value}'."
        )
    return raw_value == "true"


def _positive_integer(environment: Mapping[str, str], name: str, default: int) -> int:
    """Read a positive integer environment setting."""
    raw_value = environment.get(name, "").strip()
    if not raw_value:
        return default
    if not raw_value.isdigit() or int(raw_value) < 1:
        raise SettingsError(
            f"Environment variable {name} must be a positive whole number, got '{raw_value}'."
        )
    return int(raw_value)
