"""Ports for stored model connections, their verification and key encryption."""

from abc import ABC, abstractmethod

from harass.domain.model_connection import ModelConnection
from harass.domain.target_connection import TargetConnection


class ConnectionStore(ABC):
    """Stores connections per owner; it only ever sees encrypted API keys."""

    @abstractmethod
    def save(self, connection: ModelConnection, encrypted_api_key: str | None) -> None:
        """Save a connection while retaining an omitted API key.

        Raises: UnknownConnectionError: If ``None`` is given for a connection with no stored key.
        """

    @abstractmethod
    def get(self, connection_id: str, owner_id: str) -> ModelConnection:
        """Return one connection of the owner.

        Raises: UnknownConnectionError: If the owner has no connection with that identifier.
        """

    @abstractmethod
    def snapshot(self, connection_id: str, owner_id: str) -> tuple[ModelConnection, str]:
        """Read a connection and its encrypted key from the same stored version."""

    @abstractmethod
    def page_for_owner(self, owner_id: str, offset: int, limit: int) -> list[ModelConnection]:
        """Return one page of the owner's connections ordered by identifier."""

    @abstractmethod
    def counts_for_owner(self, owner_id: str) -> dict[str, int]:
        """Count the owner's connections in each status."""


class ConnectionVerifier(ABC):
    """Performs a minimal technical check against the endpoint."""

    @abstractmethod
    async def verify(self, target: TargetConnection) -> str | None:
        """Return an error message when model verification fails."""


class SecretCipher(ABC):
    """Protect stored secrets and decrypt them for authorized use."""

    @abstractmethod
    def encrypt(self, secret: str) -> str:
        """Return an opaque token that reveals nothing about the secret."""

    @abstractmethod
    def decrypt(self, token: str) -> str:
        """Return the secret behind a token produced by ``encrypt``.

        Raises: SecretCipherError: If the token was altered or encrypted with
        another key.
        """
