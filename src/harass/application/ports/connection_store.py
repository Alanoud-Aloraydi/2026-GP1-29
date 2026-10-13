"""Port for persisting clients' model connections and their encrypted API keys."""

from abc import ABC, abstractmethod
from collections import Counter

from harass.domain.model_connection import ModelConnection


class ConnectionStore(ABC):
    """Stores connections per owner; it only ever sees encrypted API keys."""

    def page_for_owner(self, owner_id: str, offset: int, limit: int) -> list[ModelConnection]:
        """Provide bounded pages for simple adapters; databases override this query."""
        return self.list_for_owner(owner_id)[offset : offset + limit]

    def counts_for_owner(self, owner_id: str) -> dict[str, int]:
        """Count statuses for simple adapters without exposing credentials."""
        return dict(Counter(item.status.value for item in self.list_for_owner(owner_id)))

    def snapshot(self, connection_id: str, owner_id: str) -> tuple[ModelConnection, str]:
        """Read matching metadata and encrypted credentials; databases override atomically."""
        return self.get(connection_id, owner_id), self.encrypted_api_key(connection_id, owner_id)

    @abstractmethod
    def save(self, connection: ModelConnection, encrypted_api_key: str | None) -> None:
        """Insert or update a connection; ``None`` keeps the stored key unchanged.

        Raises:
            UnknownConnectionError: If ``None`` is given for a connection with no stored key.
        """

    @abstractmethod
    def get(self, connection_id: str, owner_id: str) -> ModelConnection:
        """Return the owner's connection.

        Raises:
            UnknownConnectionError: If the owner has no connection with that identifier.
        """

    @abstractmethod
    def list_for_owner(self, owner_id: str) -> list[ModelConnection]:
        """Return the owner's connections ordered by identifier."""

    @abstractmethod
    def encrypted_api_key(self, connection_id: str, owner_id: str) -> str:
        """Return the stored encrypted key of the owner's connection.

        Raises:
            UnknownConnectionError: If the owner has no connection with that identifier.
        """
