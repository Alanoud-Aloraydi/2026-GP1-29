"""Shared ORM metadata and portable entity identifier storage."""

from sqlalchemy import String, Uuid
from sqlalchemy.orm import DeclarativeBase

ENTITY_ID = String(64).with_variant(Uuid(as_uuid=False), "postgresql")


class Base(DeclarativeBase):
    """Declarative base for the project's tables."""
