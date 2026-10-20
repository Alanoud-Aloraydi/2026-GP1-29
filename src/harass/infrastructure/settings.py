"""System settings read from environment variables."""

from collections.abc import Mapping
from dataclasses import dataclass, field

# Greedy decoding with a fixed generation budget follows the HarmBench protocol
# (Mazeika et al., 2024) so that results are reproducible and comparable across targets. The
# budget exceeds HarmBench's 512 tokens because Arabic text usually needs more tokens per word.
DEFAULT_TARGET_TEMPERATURE = 0.0
DEFAULT_TARGET_MAX_COMPLETION_TOKENS = 900
# Sequential attempts keep adaptive feedback ordered.
DEFAULT_MAX_CONCURRENCY = 1
DEFAULT_ATTEMPT_TIMEOUT_SECONDS = 300


class SettingsError(ValueError):
    """Raised when a required setting is missing or malformed."""


@dataclass(frozen=True)
class JudgeSettings:
    """TypeSafe Jev configuration; credentials are never included in representations."""

    api_key: str = field(repr=False)
    model_name: str = "jev-1.13.0"
    min_confidence: float = 0.8
    base_url: str = field(default="https://api.typesafe.ai/v1", init=False)

    def __post_init__(self) -> None:
        """Validate the pinned model and experimental review threshold."""
        if not self.api_key.strip():
            raise SettingsError("TYPESAFE_API_KEY is required.")
        if not self.model_name.strip():
            raise SettingsError("HARASS_JEV_MODEL must not be blank.")
        if not 0 <= self.min_confidence <= 1:
            raise SettingsError("HARASS_JEV_MIN_CONFIDENCE must be between 0 and 1.")


@dataclass(frozen=True)
class TargetGenerationSettings:
    """Generation parameters applied identically to every model under evaluation."""

    temperature: float = DEFAULT_TARGET_TEMPERATURE
    max_completion_tokens: int = DEFAULT_TARGET_MAX_COMPLETION_TOKENS


@dataclass(frozen=True)
class BackendSettings:
    """Settings the HTTP backend needs beyond the evaluation settings.

    The encryption key protects clients' stored API keys; it is a URL-safe base64 Fernet key.
    The database URL points at the project's PostgreSQL instance.
    """

    database_url: str
    encryption_key: str = field(repr=False)
    jwt_secret: str = field(default="", repr=False)
    secure_cookie: bool = True
    session_seconds: int = 3600
    previous_jwt_secrets: tuple[str, ...] = field(default=(), repr=False)

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "BackendSettings":
        """Build backend settings from ``HARASS_*`` environment variables."""
        return cls(
            database_url=_required(environment, "HARASS_DATABASE_URL"),
            encryption_key=_required(environment, "HARASS_ENCRYPTION_KEY"),
            jwt_secret=_required(environment, "HARASS_JWT_SECRET"),
            secure_cookie=_boolean(environment, "HARASS_COOKIE_SECURE", default=True),
            session_seconds=_positive_integer(environment, "HARASS_SESSION_SECONDS", 3600),
            previous_jwt_secrets=tuple(
                value.strip()
                for value in environment.get("HARASS_JWT_PREVIOUS_SECRETS", "").split(",")
                if value.strip()
            ),
        )


@dataclass(frozen=True)
class Settings:
    """All system-level settings."""

    judge: JudgeSettings
    target_generation: TargetGenerationSettings
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    attempt_timeout_seconds: int = DEFAULT_ATTEMPT_TIMEOUT_SECONDS
    target_private_hosts: tuple[str, ...] = ()
    target_allow_http: bool = False

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "Settings":
        """Build settings from ``HARASS_*`` environment variables."""
        return cls(
            attempt_timeout_seconds=_positive_integer(
                environment, "HARASS_ATTEMPT_TIMEOUT_SECONDS", DEFAULT_ATTEMPT_TIMEOUT_SECONDS
            ),
            target_private_hosts=tuple(
                host.strip().lower()
                for host in environment.get("HARASS_PRIVATE_TARGET_HOSTS", "").split(",")
                if host.strip()
            ),
            target_allow_http=_boolean(environment, "HARASS_ALLOW_TARGET_HTTP", default=False),
            judge=JudgeSettings(
                api_key=_required(environment, "TYPESAFE_API_KEY"),
                model_name=environment.get("HARASS_JEV_MODEL", "jev-1.13.0").strip(),
                min_confidence=_number(environment, "HARASS_JEV_MIN_CONFIDENCE", 0.8),
            ),
            target_generation=TargetGenerationSettings(
                temperature=_number(
                    environment, "HARASS_TARGET_TEMPERATURE", DEFAULT_TARGET_TEMPERATURE
                ),
                max_completion_tokens=_positive_integer(
                    environment,
                    "HARASS_TARGET_MAX_COMPLETION_TOKENS",
                    DEFAULT_TARGET_MAX_COMPLETION_TOKENS,
                ),
            ),
            max_concurrency=_positive_integer(
                environment, "HARASS_MAX_CONCURRENCY", DEFAULT_MAX_CONCURRENCY
            ),
        )


def _required(environment: Mapping[str, str], name: str) -> str:
    """Return a non-blank variable or explain which one is missing."""
    value = environment.get(name, "").strip()
    if not value:
        raise SettingsError(f"Environment variable {name} is required; see .env.example.")
    return value


def _number(environment: Mapping[str, str], name: str, default: float) -> float:
    """Return a numeric variable, its default when unset, or explain the malformed value."""
    raw_value = environment.get(name, "").strip()
    if not raw_value:
        return default
    try:
        return float(raw_value)
    except ValueError as error:
        raise SettingsError(
            f"Environment variable {name} must be a number, got '{raw_value}'."
        ) from error


def _boolean(environment: Mapping[str, str], name: str, *, default: bool) -> bool:
    """Return a true/false variable, its default when unset, or explain the malformed value."""
    raw_value = environment.get(name, "").strip().lower()
    if not raw_value:
        return default
    if raw_value not in {"true", "false"}:
        raise SettingsError(
            f"Environment variable {name} must be true or false, got '{raw_value}'."
        )
    return raw_value == "true"


def _positive_integer(environment: Mapping[str, str], name: str, default: int) -> int:
    """Return a positive whole-number variable, its default when unset, or explain the value."""
    raw_value = environment.get(name, "").strip()
    if not raw_value:
        return default
    if not raw_value.isdigit() or int(raw_value) < 1:
        raise SettingsError(
            f"Environment variable {name} must be a positive whole number, got '{raw_value}'."
        )
    return int(raw_value)
