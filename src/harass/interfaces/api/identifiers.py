"""Validate entity identifiers taken from request paths."""

from uuid import UUID

from harass.application.errors import ApplicationError


def validated_identifier(value: str, error_type: type[ApplicationError]) -> str:
    """Reject malformed entity IDs before PostgreSQL attempts to cast them."""
    try:
        return str(UUID(value))
    except ValueError as error:
        raise error_type("Record not found.") from error
