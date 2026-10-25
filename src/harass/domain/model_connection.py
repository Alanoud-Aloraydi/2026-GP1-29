"""A client's saved connection to a model under evaluation."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from harass.domain.errors import InvalidTargetConnectionError
from harass.domain.target_connection import validate_endpoint


class ConnectionStatus(StrEnum):
    """Record the technical result of the latest connection check."""

    NOT_TESTED = "not_tested"
    CONNECTED = "connected"
    FAILED = "failed"


@dataclass(frozen=True)
class ModelConnection:
    """Store owned endpoint metadata separately from encrypted keys.

    Changing the endpoint or the key resets the status to not tested, because a
    previous successful test no longer says anything about the new settings.
    """

    connection_id: str
    owner_id: str
    base_url: str
    model_name: str
    status: ConnectionStatus = ConnectionStatus.NOT_TESTED
    failure_reason: str | None = None
    last_tested_at: datetime | None = None
    revision: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        """Reject connections that could not address a model."""
        validate_endpoint(self.base_url, self.model_name)
        if self.status is ConnectionStatus.FAILED and not self.failure_reason:
            raise InvalidTargetConnectionError(
                "A failed connection must state why it failed."
            )
