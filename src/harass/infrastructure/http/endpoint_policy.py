"""Pin outbound connections to validated addresses while retaining TLS host verification."""

import asyncio
import ipaddress
import socket
from collections.abc import Iterable
from dataclasses import dataclass
from time import perf_counter
from urllib.parse import urlsplit

import httpcore
import httpx


@dataclass(frozen=True)
class EndpointPolicy:
    """Allow public HTTPS endpoints and explicitly configured private model hosts."""

    private_hosts: tuple[str, ...] = ()
    allow_http: bool = False

    def client(self, endpoint: str) -> httpx.AsyncClient:
        """Build a client without implicit proxies or cross-host redirects."""
        return httpx.AsyncClient(
            transport=self.transport(endpoint), trust_env=False, follow_redirects=False
        )

    def transport(self, endpoint: str) -> httpx.AsyncHTTPTransport:
        """Enforce scheme policy before any credentials can leave the process."""
        parsed = urlsplit(endpoint)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" and not self.allow_http and host not in self.private_hosts:
            raise httpx.ConnectError(
                "HTTP model endpoints require an explicit private-host allowance."
            )
        transport = httpx.AsyncHTTPTransport(trust_env=False)
        # HTTPX 0.28 has no public network-backend argument; confine its pinned pool hook here.
        transport._pool = httpcore.AsyncConnectionPool(
            network_backend=RestrictedNetwork(self.private_hosts)
        )
        return transport


class RestrictedNetwork(httpcore.AsyncNetworkBackend):
    """Validate DNS results and connect to the selected IP without resolving it again."""

    def __init__(self, private_hosts: tuple[str, ...]) -> None:
        """Bind the explicit host exceptions and the existing AnyIO TCP backend."""
        self._private_hosts = frozenset(host.lower() for host in private_hosts)
        self._backend = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        """Reject non-global addresses unless this exact hostname is explicitly permitted."""
        deadline = perf_counter() + min(timeout or 10, 10)
        try:
            async with asyncio.timeout(min(timeout or 10, 10)):
                addresses = await asyncio.get_running_loop().getaddrinfo(
                    host, port, type=socket.SOCK_STREAM
                )
        except (TimeoutError, OSError) as error:
            raise httpcore.ConnectError("Endpoint address resolution failed.") from error
        ips = [str(address[4][0]) for address in addresses]
        if not ips or (
            host.lower() not in self._private_hosts
            and any(not ipaddress.ip_address(ip).is_global for ip in ips)
        ):
            raise httpcore.ConnectError("Endpoint network policy denied this address.")
        for ip in list(dict.fromkeys(ips))[:8]:
            remaining = deadline - perf_counter()
            if remaining <= 0:
                break
            try:
                return await self._backend.connect_tcp(
                    ip, port, min(remaining, 3), local_address, socket_options
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout):
                continue
        raise httpcore.ConnectError("Could not connect to a permitted endpoint address.")

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        """Model endpoints cannot address local Unix sockets."""
        raise httpcore.ConnectError("Unix model sockets are not permitted.")

    async def sleep(self, seconds: float) -> None:
        """Delegate transport retry delays."""
        await self._backend.sleep(seconds)
