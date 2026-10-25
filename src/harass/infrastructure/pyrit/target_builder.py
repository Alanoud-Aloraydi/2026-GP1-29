"""Build PyRIT targets for evaluated models and the judge."""

from pyrit.prompt_target import OpenAIChatTarget, PromptTarget
from pyrit.prompt_target.common.target_capabilities import (
    CapabilityHandlingPolicy,
    CapabilityName,
    TargetCapabilities,
    UnsupportedCapabilityBehavior,
)
from pyrit.prompt_target.common.target_configuration import TargetConfiguration

from harass.domain.target_connection import TargetConnection
from harass.infrastructure.http.endpoint_policy import EndpointPolicy
from harass.infrastructure.pyrit.judge_request_audit import (
    audited_client,
)
from harass.infrastructure.settings import (
    JudgeSettings,
    TargetGenerationSettings,
)


def _judge_configuration(
    *, supports_system_prompt: bool, supports_json_output: bool = False
) -> TargetConfiguration:
    """Configure judge instructions and system-prompt support.

    Earlier DeepSeek-R1 distilled models advise against system prompts, while
    DeepSeek-R1-0528 supports them, so the capability follows the configured
    judge model.
    """
    adapt = UnsupportedCapabilityBehavior.ADAPT
    return TargetConfiguration(
        capabilities=TargetCapabilities(
            supports_multi_turn=True,
            supports_editable_history=True,
            supports_system_prompt=supports_system_prompt,
            supports_json_output=supports_json_output,
        ),
        policy=CapabilityHandlingPolicy(
            behaviors={
                CapabilityName.MULTI_TURN: UnsupportedCapabilityBehavior.RAISE,
                CapabilityName.SYSTEM_PROMPT: adapt,
                CapabilityName.JSON_SCHEMA: adapt,
            }
        ),
    )


def build_target(
    connection: TargetConnection,
    generation: TargetGenerationSettings,
    *,
    endpoint_policy: EndpointPolicy | None = None,
) -> OpenAIChatTarget:
    """Build the client target with shared generation settings."""
    return OpenAIChatTarget(
        endpoint=connection.base_url,
        model_name=connection.model_name,
        api_key=connection.api_key,
        temperature=generation.temperature,
        max_completion_tokens=generation.max_completion_tokens,
        max_requests_per_minute=connection.max_requests_per_minute,
        httpx_client_kwargs={
            "http_client": endpoint_policy.client(connection.base_url)
        }
        if endpoint_policy
        else None,
    )


def build_judge(settings: JudgeSettings) -> OpenAIChatTarget:
    """Build the configured judge chat target."""
    extra: dict[str, object] = {}
    if settings.token_limit_parameter == "max_tokens":
        extra["max_tokens"] = settings.max_completion_tokens
    if settings.keep_alive is not None:
        extra["extra_body"] = {"keep_alive": settings.keep_alive}
    target = OpenAIChatTarget(
        endpoint=settings.base_url,
        model_name=settings.model_name,
        api_key=settings.api_key,
        temperature=settings.temperature,
        # Ollama's OpenAI compatibility layer accepts max_tokens, not
        # max_completion_tokens.
        # https://docs.ollama.com/api/openai-compatibility
        max_completion_tokens=settings.max_completion_tokens
        if settings.token_limit_parameter == "max_completion_tokens"
        else None,
        extra_body_parameters=extra or None,
        httpx_client_kwargs={"http_client": audited_client()},
        custom_configuration=_judge_configuration(
            supports_system_prompt=settings.supports_system_prompt,
            supports_json_output=settings.supports_json_output,
        ),
    )
    return target


async def close_target(target: PromptTarget) -> None:
    """Close an owned OpenAI client before its event loop ends.

    PyRIT 1.1.0 exposes no public disposal method. Its pinned OpenAITarget
    stores the SDK client in `_async_client`; this adapter confines that
    compatibility hook here. Caller-supplied non-OpenAI scripted targets have
    no network client to dispose.
    """
    if (
        isinstance(target, OpenAIChatTarget)
        and target._async_client is not None
    ):
        await target._async_client.close()
