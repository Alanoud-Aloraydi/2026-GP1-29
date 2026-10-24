"""Connection details of the model under evaluation."""

from dataclasses import dataclass, field
from urllib.parse import urlsplit

from harass.domain.errors import InvalidTargetConnectionError


def validate_endpoint(base_url: str, model_name: str) -> None:
    """Validate endpoint URLs without exposing credentials."""
    try:
        parsed = urlsplit(base_url)
        port = parsed.port
        valid = parsed.scheme in {"http", "https"} and bool(parsed.hostname)
    except ValueError as error:
        raise InvalidTargetConnectionError(
            "A valid HTTP or HTTPS endpoint is required."
        ) from error
    if (
        not valid
        or len(base_url) > 2048
        or any(c.isspace() or not c.isprintable() for c in base_url)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port == 0
    ):
        raise InvalidTargetConnectionError(
            "Use an HTTP or HTTPS endpoint without "
            "credentials, query or fragment."
        )
    if not 1 <= len(model_name.strip()) <= 200 or any(
        ord(c) < 32 for c in model_name
    ):
        raise InvalidTargetConnectionError(
            "Model name must contain 1-200 printable characters."
        )


@dataclass(frozen=True)
class TargetConnection:
    """Describe the client-supplied evaluation endpoint.

    The API key is excluded from the representation so that it never reaches
    logs.
    """

    base_url: str
    model_name: str
    api_key: str = field(repr=False)
    max_requests_per_minute: int | None = None
    connection_revision: int | None = None

    def __post_init__(self) -> None:
        """Reject connections that could not address a model."""
        validate_endpoint(self.base_url, self.model_name)
        if (
            not self.api_key.strip()
            or len(self.api_key) > 8192
            or any(ord(c) < 32 for c in self.api_key)
        ):
            raise InvalidTargetConnectionError("An API key is required.")
        if (
            self.max_requests_per_minute is not None
            and self.max_requests_per_minute < 1
        ):
            raise InvalidTargetConnectionError(
                "The request rate limit must be at least one."
            )
