"""Owned model connection metadata and encrypted credentials."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from harass.infrastructure.persistence.tables.base import ENTITY_ID, Base


class ConnectionRow(Base):
    """A client's model connection and its encrypted API key."""

    __tablename__ = "connections"
    __table_args__ = (
        UniqueConstraint(
            "connection_id", "owner_id", name="uq_connections_identity_owner"
        ),
        ForeignKeyConstraint(
            ["owner_id"], ["users.user_id"], name="fk_connections_owner"
        ),
        CheckConstraint(
            "status IN ('not_tested', 'connected', 'failed')",
            name="ck_connections_status",
        ),
        CheckConstraint("revision >= 0", name="ck_connections_revision"),
    )

    connection_id: Mapped[str] = mapped_column(ENTITY_ID, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ENTITY_ID, index=True)
    base_url: Mapped[str] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    failure_reason: Mapped[str | None] = mapped_column(Text, default=None)
    last_tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    encrypted_api_key: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
