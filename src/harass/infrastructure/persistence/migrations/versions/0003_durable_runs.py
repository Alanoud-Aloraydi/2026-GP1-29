"""Add durable jobs, fenced worker slots and paged attempt evidence."""

import sqlalchemy as sa
from alembic import op

revision: str = "0003_durable_runs"
down_revision: str | None = "0002_research_limits"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Apply this schema revision."""
    op.add_column(
        "runs", sa.Column("resumable", sa.Boolean(), server_default=sa.false(), nullable=False)
    )
    op.create_table(
        "worker_slots",
        sa.Column("slot_key", sa.String(length=64), nullable=False),
        sa.Column("worker_id", sa.String(length=64), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("slot_key"),
    )
    op.create_table(
        "run_jobs",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("target_endpoint", sa.Text(), nullable=False),
        sa.Column("execution_profile", sa.String(length=64), nullable=False),
        sa.Column("plan_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("checkpoint", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(length=64), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(op.f("ix_run_jobs_lease_until"), "run_jobs", ["lease_until"], unique=False)
    op.create_table(
        "run_outcomes",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("case_index", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("metric_document", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("run_id", "case_index", "attempt_number"),
    )
    op.add_column(
        "runs", sa.Column("total_cases", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "runs", sa.Column("completed_cases", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "runs", sa.Column("completed_attempts", sa.Integer(), server_default="0", nullable=False)
    )


def downgrade() -> None:
    """Reverse this schema revision."""
    op.drop_column("runs", "resumable")
    op.drop_column("runs", "completed_attempts")
    op.drop_column("runs", "completed_cases")
    op.drop_column("runs", "total_cases")
    op.drop_table("run_outcomes")
    op.drop_index(op.f("ix_run_jobs_lease_until"), table_name="run_jobs")
    op.drop_table("run_jobs")
    op.drop_table("worker_slots")
