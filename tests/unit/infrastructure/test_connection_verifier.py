"""Tests for the OpenAI-compatible connection verifier, with transport stubbed."""

import httpx
import pytest

from harass.domain.target_connection import TargetConnection
from harass.infrastructure.http.openai_connection_verifier import OpenAIConnectionVerifier

TARGET = TargetConnection(base_url="https://api.invalid/v1", model_name="model", api_key="k")


def verifier_with(handler: object) -> OpenAIConnectionVerifier:
    """Return a verifier whose client uses the given mock transport handler."""
    verifier = OpenAIConnectionVerifier()
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    original = httpx.AsyncClient

    def patched(**kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("timeout", None)
        return original(transport=transport)

    verifier._client_factory = patched  # type: ignore[assignment]
    return verifier


async def run(handler: object) -> str | None:
    """Verify the fixed target against a transport handler."""
    return await verifier_with(handler).verify(TARGET)


async def test_served_model_passes() -> None:
    """The target model being listed means the connection is good."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer k"
        return httpx.Response(200, json={"data": [{"id": "model"}]})

    assert await run(handler) is None


async def test_unauthorized_is_reported() -> None:
    """A 401 is reported without echoing the key."""
    result = await run(lambda request: httpx.Response(401, json={}))

    assert result is not None
    assert "401" in result and "k" not in result.split()


async def test_absent_model_is_reported() -> None:
    """A reachable endpoint that lacks the model fails with a clear reason."""
    result = await run(lambda request: httpx.Response(200, json={"data": [{"id": "other"}]}))

    assert result is not None and "model" in result


async def test_transport_error_is_reported() -> None:
    """A connection error becomes a short reason, not an exception."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    assert "reach" in (await run(handler) or "")


def test_public_targets_require_https_and_disable_redirects() -> None:
    """A private HTTP exception is explicit and clients cannot forward keys through redirects."""
    import pytest

    from harass.infrastructure.http.endpoint_policy import EndpointPolicy

    with pytest.raises(httpx.ConnectError):
        EndpointPolicy().transport("http://target.example/v1")
    transport = EndpointPolicy(("localhost",)).transport("http://localhost:9000/v1")
    assert transport is not None


async def test_dns_policy_blocks_mixed_addresses_and_pins_public_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mixed public/private DNS answers are rejected before opening a socket."""
    import asyncio
    import socket
    from unittest.mock import AsyncMock

    import httpcore
    import pytest

    from harass.infrastructure.http.endpoint_policy import RestrictedNetwork

    loop = asyncio.get_running_loop()
    resolve = AsyncMock(
        return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ]
    )
    monkeypatch.setattr(loop, "getaddrinfo", resolve)
    backend = RestrictedNetwork(())
    connect = AsyncMock()
    monkeypatch.setattr(backend._backend, "connect_tcp", connect)
    with pytest.raises(httpcore.ConnectError, match="denied"):
        await backend.connect_tcp("target.example", 443)
    connect.assert_not_awaited()
    resolve.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
    await backend.connect_tcp("target.example", 443)
    assert connect.call_args.args[:2] == ("8.8.8.8", 443)
