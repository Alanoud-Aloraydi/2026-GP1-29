"""Verify model availability and generation on compatible endpoints."""

import asyncio

import httpx

from harass.application.ports.connection_verifier import ConnectionVerifier
from harass.domain.target_connection import TargetConnection
from harass.infrastructure.http.endpoint_policy import EndpointPolicy

DEFAULT_TIMEOUT_SECONDS = 15.0


class OpenAIConnectionVerifier(ConnectionVerifier):
    """Verify model discovery and a bounded neutral text-generation request."""

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
        """Check model listing and generation; return any failure reason."""
        endpoint = target.base_url.rstrip("/")
        headers = {"Authorization": f"Bearer {target.api_key}"}
        try:
            transport = (
                self._endpoint_policy.transport(target.base_url)
                if self._endpoint_policy
                else None
            )
            async with (
                asyncio.timeout(self._timeout_seconds),
                self._client_factory(
                    timeout=self._timeout_seconds,
                    transport=transport,
                    trust_env=False,
                    follow_redirects=False,
                ) as client,
            ):
                response = await client.get(
                    endpoint + "/models", headers=headers
                )
                if failure := _http_failure(response):
                    return failure
                served = [model["id"] for model in response.json()["data"]]
                if target.model_name not in served:
                    return "The endpoint does not serve the selected model."
                response = await client.post(
                    endpoint + "/chat/completions",
                    headers=headers,
                    json={
                        "model": target.model_name,
                        "messages": [
                            {
                                "role": "user",
                                "content": "Reply with the word Hello.",
                            }
                        ],
                        "max_completion_tokens": 900,
                        "temperature": 0,
                    },
                )
                if failure := _http_failure(response):
                    return failure
                text = response.json()["choices"][0]["message"]["content"]
                if not isinstance(text, str) or not text.strip():
                    return "The model did not produce a usable text response."
        except (httpx.HTTPError, TimeoutError) as error:
            return f"Could not reach the endpoint: {type(error).__name__}."
        except (ValueError, KeyError, TypeError, IndexError):
            return "The endpoint did not return an OpenAI-compatible response."
        return None


def _http_failure(response: httpx.Response) -> str | None:
    """Classify HTTP failures without returning provider bodies or."""
    if response.status_code == 401:
        return "401 Unauthorized: the API key was rejected."
    if response.status_code >= 400:
        return f"The endpoint returned HTTP {response.status_code}."
    return None
