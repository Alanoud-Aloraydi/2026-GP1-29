"""Port for checking that a model endpoint is reachable with the given credentials."""

from abc import ABC, abstractmethod

from harass.domain.target_connection import TargetConnection


class ConnectionVerifier(ABC):
    """Performs a minimal technical check against the endpoint."""

    @abstractmethod
    async def verify(self, target: TargetConnection) -> str | None:
        """Return ``None`` when the endpoint serves the model, otherwise a short reason."""
