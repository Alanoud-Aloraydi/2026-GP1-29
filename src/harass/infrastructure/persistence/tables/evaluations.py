"""Evaluation lifecycle, reports and durable worker checkpoints."""

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
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from harass.infrastructure.persistence.tables.base import ENTITY_ID, Base


class RunRow(Base):
    """One evaluation run and, once complete, its report document."""

    __tablename__ = "runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id"], ["users.user_id"], name="fk_runs_owner"
        ),
        ForeignKeyConstraint(
            ["connection_id", "owner_id"],
            ["connections.connection_id", "connections.owner_id"],
            name="fk_runs_connection_owner",
        ),
        CheckConstraint(
            (
                "status IN ('pending', 'running', 'completed', "
                "'failed', 'cancelled')"
            ),
            name="ck_runs_status",
        ),
        CheckConstraint(
            (
                "total_cases >= 0 AND completed_cases >= 0 AND "
                "completed_cases <= total_cases AND "
                "completed_attempts >= 0"
            ),
            name="ck_runs_progress",
        ),
    )

    run_id: Mapped[str] = mapped_column(ENTITY_ID, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ENTITY_ID, index=True)
    connection_id: Mapped[str] = mapped_column(ENTITY_ID)
    target_model: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    error: Mapped[str | None] = mapped_column(Text, default=None)
    total_cases: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    completed_cases: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    completed_attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    resumable: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    lifecycle_events: Mapped[list[dict[str, str]]] = mapped_column(
        JSON, default=list
    )
    report: Mapped["ReportRow | None"] = relationship(
        back_populates="run", cascade="all, delete-orphan", uselist=False
    )


class ReportRow(Base):
    """The serialized report document of a completed run."""

    __tablename__ = "reports"

    run_id: Mapped[str] = mapped_column(
        ENTITY_ID,
        ForeignKey("runs.run_id", ondelete="CASCADE"),
        primary_key=True,
    )
    document: Mapped[dict[str, Any]] = mapped_column(JSON)
    run: Mapped[RunRow] = relationship(back_populates="report")


class RunJobRow(Base):
    """Persist immutable inputs and recoverable execution progress."""

    __tablename__ = "run_jobs"
    run_id: Mapped[str] = mapped_column(
        ENTITY_ID, ForeignKey("runs.run_id"), primary_key=True
    )
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON)
    target_endpoint: Mapped[str] = mapped_column(Text)
    execution_profile: Mapped[str] = mapped_column(String(64))
    connection_revision: Mapped[int | None] = mapped_column(Integer)
    plan_fingerprint: Mapped[str | None] = mapped_column(String(64))
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkerSlotRow(Base):
    """Serialize worker access to a shared judge service."""

    __tablename__ = "worker_slots"
    slot_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    worker_id: Mapped[str] = mapped_column(String(64))
    lease_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkerPresenceRow(Base):
    """Record shared-service worker liveness without client data."""

    __tablename__ = "worker_presence"
    slot_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RunOutcomeRow(Base):
    """Store an attempt with separate statistical data and evidence."""

    __tablename__ = "run_outcomes"
    run_id: Mapped[str] = mapped_column(
        ENTITY_ID, ForeignKey("runs.run_id"), primary_key=True
    )
    case_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    document: Mapped[dict[str, Any]] = mapped_column(JSON)
    metric_document: Mapped[dict[str, Any]] = mapped_column(JSON)


Index(
    "uq_runs_active_owner",
    RunRow.owner_id,
    unique=True,
    postgresql_where=text(
        "status IN ('pending', 'running') OR resumable = true"
    ),
    sqlite_where=text("status IN ('pending', 'running') OR resumable = 1"),
)
