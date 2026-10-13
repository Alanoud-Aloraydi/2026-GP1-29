"""System settings read from environment variables."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

# Greedy decoding with a fixed generation budget follows the HarmBench protocol
# (Mazeika et al., 2024) so that results are reproducible and comparable across targets. The
# budget exceeds HarmBench's 512 tokens because Arabic text usually needs more tokens per word.
DEFAULT_TARGET_TEMPERATURE = 0.0
DEFAULT_TARGET_MAX_COMPLETION_TOKENS = 900
# DeepSeek uses 0.6 for DeepSeek-R1-0528 and recommends 0.5-0.7 for earlier R1 distilled models.
DEFAULT_JUDGE_TEMPERATURE = 0.6
# Reasoning models can generate until the server context is exhausted; the bound keeps every
# judge call finite and must leave room for the scoring prompt within the server context length.
DEFAULT_JUDGE_MAX_COMPLETION_TOKENS = 4096
# Verdicts per response for the majority vote; odd so a true/false verdict always has a majority.
DEFAULT_JUDGE_VOTES = 3
# One case at a time suits a single local judge GPU and the rate limits of hosted targets.
DEFAULT_MAX_CONCURRENCY = 1
DEFAULT_ATTEMPT_TIMEOUT_SECONDS = 300


class SettingsError(ValueError):
    """Raised when a required setting is missing or malformed."""


@dataclass(frozen=True)
class JudgeSettings:
    """Endpoint and sampling of the judge model; the API key is kept out of representations."""

    base_url: str
    model_name: str
    api_key: str = field(repr=False)
    temperature: float = DEFAULT_JUDGE_TEMPERATURE
    max_completion_tokens: int = DEFAULT_JUDGE_MAX_COMPLETION_TOKENS
    supports_system_prompt: bool = True
    votes: int = DEFAULT_JUDGE_VOTES
    token_limit_parameter: str = "max_completion_tokens"
    keep_alive: str | None = None
    supports_json_output: bool = False

    def __post_init__(self) -> None:
        """Reject an even number of votes, which could leave a true/false verdict tied."""
        if self.votes < 1 or self.votes % 2 == 0:
            raise SettingsError(
                f"The number of judge votes must be odd and positive, got {self.votes}."
            )
        if self.token_limit_parameter not in {"max_tokens", "max_completion_tokens"}:
            raise SettingsError(
                "Judge token limit parameter must be max_tokens or max_completion_tokens."
            )
        if self.keep_alive is not None and (
            not re.fullmatch(r"\d+[smh]", self.keep_alive) or int(self.keep_alive[:-1]) < 1
        ):
            raise SettingsError("Judge keep-alive must be a positive duration such as 30m.")


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
                base_url=_required(environment, "HARASS_JUDGE_BASE_URL"),
                model_name=_required(environment, "HARASS_JUDGE_MODEL"),
                api_key=_required(environment, "HARASS_JUDGE_API_KEY"),
                temperature=_number(
                    environment, "HARASS_JUDGE_TEMPERATURE", DEFAULT_JUDGE_TEMPERATURE
                ),
                max_completion_tokens=_positive_integer(
                    environment,
                    "HARASS_JUDGE_MAX_COMPLETION_TOKENS",
                    DEFAULT_JUDGE_MAX_COMPLETION_TOKENS,
                ),
                supports_system_prompt=_boolean(
                    environment, "HARASS_JUDGE_SUPPORTS_SYSTEM_PROMPT", default=True
                ),
                votes=_positive_integer(environment, "HARASS_JUDGE_VOTES", DEFAULT_JUDGE_VOTES),
                token_limit_parameter=environment.get(
                    "HARASS_JUDGE_TOKEN_LIMIT_PARAMETER", "max_completion_tokens"
                ).strip(),
                keep_alive=environment.get("HARASS_JUDGE_KEEP_ALIVE", "").strip() or None,
                supports_json_output=_boolean(
                    environment, "HARASS_JUDGE_JSON_OUTPUT", default=False
                ),
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
