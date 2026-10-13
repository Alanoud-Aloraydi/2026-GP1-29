"""SQLAlchemy table definitions for connections and runs."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

ENTITY_ID = String(64).with_variant(Uuid(as_uuid=False), "postgresql")


class Base(DeclarativeBase):
    """Declarative base for the project's tables."""


class UserRow(Base):
    """Account identity and salted password hash."""

    __tablename__ = "users"
    user_id: Mapped[str] = mapped_column(ENTITY_ID, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthenticationSessionRow(Base):
    """Revocable JWT session metadata; raw tokens are never persisted."""

    __tablename__ = "authentication_sessions"
    session_id: Mapped[str] = mapped_column(ENTITY_ID, primary_key=True)
    user_id: Mapped[str] = mapped_column(ENTITY_ID, ForeignKey("users.user_id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ConnectionRow(Base):
    """A client's model connection and its encrypted API key."""

    __tablename__ = "connections"
    __table_args__ = (
        UniqueConstraint("connection_id", "owner_id", name="uq_connections_identity_owner"),
        ForeignKeyConstraint(["owner_id"], ["users.user_id"], name="fk_connections_owner"),
        CheckConstraint(
            "status IN ('not_tested', 'connected', 'failed')", name="ck_connections_status"
        ),
        CheckConstraint("revision >= 0", name="ck_connections_revision"),
    )

    connection_id: Mapped[str] = mapped_column(ENTITY_ID, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ENTITY_ID, index=True)
    base_url: Mapped[str] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    failure_reason: Mapped[str | None] = mapped_column(Text, default=None)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    encrypted_api_key: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RunRow(Base):
    """One evaluation run and, once complete, its report document."""

    __tablename__ = "runs"
    __table_args__ = (
        ForeignKeyConstraint(["owner_id"], ["users.user_id"], name="fk_runs_owner"),
        ForeignKeyConstraint(
            ["connection_id", "owner_id"],
            ["connections.connection_id", "connections.owner_id"],
            name="fk_runs_connection_owner",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_runs_status",
        ),
        CheckConstraint(
            "total_cases >= 0 AND completed_cases >= 0 AND completed_cases <= total_cases "
            "AND completed_attempts >= 0",
            name="ck_runs_progress",
        ),
    )

    run_id: Mapped[str] = mapped_column(ENTITY_ID, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ENTITY_ID, index=True)
    connection_id: Mapped[str] = mapped_column(ENTITY_ID)
    target_model: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    total_cases: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    completed_cases: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    completed_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    resumable: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lifecycle_events: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    report: Mapped["ReportRow | None"] = relationship(
        back_populates="run", cascade="all, delete-orphan", uselist=False
    )


Index(
    "uq_runs_active_owner",
    RunRow.owner_id,
    unique=True,
    postgresql_where=text("status IN ('pending', 'running') OR resumable = true"),
    sqlite_where=text("status IN ('pending', 'running') OR resumable = 1"),
)


class ReportRow(Base):
    """The serialized report document of a completed run."""

    __tablename__ = "reports"

    run_id: Mapped[str] = mapped_column(
        ENTITY_ID, ForeignKey("runs.run_id", ondelete="CASCADE"), primary_key=True
    )
    document: Mapped[dict[str, Any]] = mapped_column(JSON)
    run: Mapped[RunRow] = relationship(back_populates="report")


class GeneratedPromptRow(Base):
    """Exact generated text, separate from the human-authored dataset."""

    __tablename__ = "generated_prompts"
    content_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PromptFindingRow(Base):
    """One automatically judged defect with its reproducible research evidence."""

    __tablename__ = "prompt_findings"
    __table_args__ = (UniqueConstraint("run_id", "case_id", "variant_id", "attempt_number"),)
    finding_id: Mapped[str] = mapped_column(ENTITY_ID, primary_key=True)
    content_sha256: Mapped[str] = mapped_column(
        String(64), ForeignKey("generated_prompts.content_sha256"), index=True
    )
    run_id: Mapped[str] = mapped_column(ENTITY_ID, ForeignKey("runs.run_id"), index=True)
    case_id: Mapped[str] = mapped_column(String(128))
    variant_id: Mapped[str] = mapped_column(Text)
    attempt_number: Mapped[int] = mapped_column(Integer)
    axis: Mapped[str] = mapped_column(String(2))
    target_model: Mapped[str] = mapped_column(Text)
    target_endpoint: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON)


class RequestLimitRow(Base):
    """Shared fixed-window request counters without raw client identifiers."""

    __tablename__ = "request_limits"
    bucket_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[int] = mapped_column(Integer, index=True)
    request_count: Mapped[int] = mapped_column(Integer)


class RunJobRow(Base):
    """Immutable run inputs and the current recoverable execution checkpoint."""

    __tablename__ = "run_jobs"
    run_id: Mapped[str] = mapped_column(ENTITY_ID, ForeignKey("runs.run_id"), primary_key=True)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON)
    target_endpoint: Mapped[str] = mapped_column(Text)
    execution_profile: Mapped[str] = mapped_column(String(64))
    connection_revision: Mapped[int | None] = mapped_column(Integer)
    plan_fingerprint: Mapped[str | None] = mapped_column(String(64))
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkerSlotRow(Base):
    """A shared judge lease prevents several workers from overloading one GPU."""

    __tablename__ = "worker_slots"
    slot_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    worker_id: Mapped[str] = mapped_column(String(64))
    lease_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkerPresenceRow(Base):
    """Last worker heartbeat for a shared judge service, without client data."""

    __tablename__ = "worker_presence"
    slot_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RunOutcomeRow(Base):
    """One committed attempt with separate compact statistical data and full evidence."""

    __tablename__ = "run_outcomes"
    run_id: Mapped[str] = mapped_column(ENTITY_ID, ForeignKey("runs.run_id"), primary_key=True)
    case_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    document: Mapped[dict[str, Any]] = mapped_column(JSON)
    metric_document: Mapped[dict[str, Any]] = mapped_column(JSON)
