"""Check model endpoints using the supplied credentials."""

from abc import ABC, abstractmethod

from harass.domain.target_connection import TargetConnection


class ConnectionVerifier(ABC):
    """Performs a minimal technical check against the endpoint."""

    @abstractmethod
    async def verify(self, target: TargetConnection) -> str | None:
        """Return an error message when model verification fails."""
