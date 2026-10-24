"""Account identities, revocable sessions and expiring actions."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from harass.infrastructure.persistence.tables.base import ENTITY_ID, Base


class UserRow(Base):
    """Account identity and salted password hash."""

    __tablename__ = "users"
    user_id: Mapped[str] = mapped_column(ENTITY_ID, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class AuthenticationSessionRow(Base):
    """Revocable JWT session metadata; raw tokens are never persisted."""

    __tablename__ = "authentication_sessions"
    session_id: Mapped[str] = mapped_column(ENTITY_ID, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ENTITY_ID, ForeignKey("users.user_id"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    refresh_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    refresh_hash: Mapped[str | None] = mapped_column(String(64))
    used_refresh_hashes: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default="[]"
    )


class AccountActionRow(Base):
    """Store a purpose-bound action and the credential snapshot it permits."""

    __tablename__ = "account_actions"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('verify_email', 'reset_password')",
            name="ck_account_action_purpose",
        ),
    )

    action_id: Mapped[str] = mapped_column(ENTITY_ID, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ENTITY_ID, ForeignKey("users.user_id"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(32))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    credential_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
