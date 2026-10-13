"""Connection verifier that checks an OpenAI-compatible endpoint serves the target model."""

import httpx

from harass.application.ports.connection_verifier import ConnectionVerifier
from harass.domain.target_connection import TargetConnection
from harass.infrastructure.http.endpoint_policy import EndpointPolicy

DEFAULT_TIMEOUT_SECONDS = 15.0


class OpenAIConnectionVerifier(ConnectionVerifier):
    """Lists the endpoint's models and checks the target model is among them.

    This is a technical reachability check, not a safety evaluation. Any failure is reported as a
    short reason for the client to act on; the API key never appears in that reason.
    """

    def __init__(
        self,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        *,
        endpoint_policy: EndpointPolicy | None = None,
    ) -> None:
        """Store the request timeout."""
        self._timeout_seconds = timeout_seconds
        self._client_factory = httpx.AsyncClient
        self._endpoint_policy = endpoint_policy

    async def verify(self, target: TargetConnection) -> str | None:
        """Return ``None`` when the model is served, otherwise a short reason."""
        url = f"{target.base_url.rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {target.api_key}"}
        try:
            transport = (
                self._endpoint_policy.transport(target.base_url) if self._endpoint_policy else None
            )
            async with self._client_factory(
                timeout=self._timeout_seconds,
                transport=transport,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                response = await client.get(url, headers=headers)
        except httpx.HTTPError as error:
            return f"Could not reach the endpoint: {type(error).__name__}."
        if response.status_code == 401:
            return "401 Unauthorized: the API key was rejected."
        if response.status_code >= 400:
            return f"The endpoint returned HTTP {response.status_code}."
        try:
            served = [model["id"] for model in response.json()["data"]]
        except (ValueError, KeyError, TypeError):
            return "The endpoint did not return an OpenAI-compatible model list."
        if target.model_name not in served:
            return f"The endpoint does not serve the model '{target.model_name}'."
        return None
