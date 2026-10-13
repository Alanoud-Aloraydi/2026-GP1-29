"""Shared admission control for expensive HTTP operations."""

from abc import ABC, abstractmethod


class RequestLimiter(ABC):
    """Atomically bound requests across application workers."""

    @abstractmethod
    def consume(self, key: str, limit: int, window_seconds: int = 60) -> int:
        """Return zero if admitted, otherwise seconds until the current window ends."""
