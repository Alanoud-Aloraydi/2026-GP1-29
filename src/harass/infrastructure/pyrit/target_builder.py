"""Construction of PyRIT chat targets for the model under evaluation and the judge."""

from pyrit.prompt_target import OpenAIChatTarget, PromptTarget

from harass.domain.target_connection import TargetConnection
from harass.infrastructure.http.endpoint_policy import EndpointPolicy
from harass.infrastructure.pyrit.scoring.jev_scorer import JevJudge
from harass.infrastructure.settings import JudgeSettings, TargetGenerationSettings


def build_target(
    connection: TargetConnection,
    generation: TargetGenerationSettings,
    *,
    endpoint_policy: EndpointPolicy | None = None,
) -> OpenAIChatTarget:
    """Return a chat target for the client's model with the system-wide generation settings."""
    return OpenAIChatTarget(
        endpoint=connection.base_url,
        model_name=connection.model_name,
        api_key=connection.api_key,
        temperature=generation.temperature,
        max_completion_tokens=generation.max_completion_tokens,
        max_requests_per_minute=connection.max_requests_per_minute,
        httpx_client_kwargs={"http_client": endpoint_policy.client(connection.base_url)}
        if endpoint_policy
        else None,
    )


def build_judge(settings: JudgeSettings) -> JevJudge:
    """Build the sole hosted decision judge; no generative judge is created."""
    return JevJudge(
        api_key=settings.api_key, model=settings.model_name, min_confidence=settings.min_confidence
    )


async def close_target(target: PromptTarget | JevJudge) -> None:
    """Close an owned OpenAI client before its event loop ends.

    PyRIT 1.1.0 exposes no public disposal method. Its pinned OpenAITarget stores the
    SDK client in `_async_client`; this adapter confines that compatibility hook here.
    Caller-supplied non-OpenAI scripted targets have no network client to dispose.
    """
    if isinstance(target, JevJudge):
        await target.aclose()
    if isinstance(target, OpenAIChatTarget) and target._async_client is not None:
        await target._async_client.close()
