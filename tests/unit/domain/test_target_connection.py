"""Tests for target connection invariants."""

import pytest

from harass.domain.errors import InvalidTargetConnectionError
from harass.domain.target_connection import TargetConnection


def test_representation_never_contains_the_api_key() -> None:
    """Logging a connection cannot leak the client's secret."""
    connection = TargetConnection(
        base_url="https://api.example.com/v1",
        model_name="model",
        api_key="secret-value",
    )

    assert "secret-value" not in repr(connection)


@pytest.mark.parametrize(
    ("base_url", "model_name", "api_key", "max_requests_per_minute"),
    [
        ("api.example.com/v1", "model", "key", None),
        ("https://api.example.com/v1", " ", "key", None),
        ("https://api.example.com/v1", "model", "", None),
        ("https://api.example.com/v1", "model", "key", 0),
    ],
)
def test_rejects_incomplete_or_malformed_connections(
    base_url: str,
    model_name: str,
    api_key: str,
    max_requests_per_minute: int | None,
) -> None:
    """A connection must be able to address a model."""
    with pytest.raises(InvalidTargetConnectionError):
        TargetConnection(
            base_url=base_url,
            model_name=model_name,
            api_key=api_key,
            max_requests_per_minute=max_requests_per_minute,
        )
