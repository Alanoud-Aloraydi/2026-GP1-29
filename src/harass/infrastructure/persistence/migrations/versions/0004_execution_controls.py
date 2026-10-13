"""Connection revisions and explicit evaluation lifecycle history."""

import sqlalchemy as sa
from alembic import op

revision = "0004_execution_controls"
down_revision = "0003_durable_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Preserve existing evidence without fabricating historical start times."""
    op.create_table(
        "worker_presence",
        sa.Column("slot_key", sa.String(64), primary_key=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("users", sa.Column("created_at", sa.DateTime(timezone=True)))
    op.add_column(
        "connections", sa.Column("revision", sa.Integer(), nullable=False, server_default="0")
    )
    for name in ("created_at", "updated_at"):
        op.add_column("connections", sa.Column(name, sa.DateTime(timezone=True)))
    op.add_column("runs", sa.Column("started_at", sa.DateTime(timezone=True)))
    op.add_column(
        "runs", sa.Column("lifecycle_events", sa.JSON(), nullable=False, server_default="[]")
    )
    op.add_column("run_jobs", sa.Column("connection_revision", sa.Integer()))
    op.create_index(
        "uq_runs_active_owner",
        "runs",
        ["owner_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running') OR resumable = true"),
        sqlite_where=sa.text("status IN ('pending', 'running') OR resumable = 1"),
    )


def downgrade() -> None:
    """Remove only the fields introduced by this revision."""
    op.drop_index("uq_runs_active_owner", table_name="runs")
    op.drop_column("run_jobs", "connection_revision")
    op.drop_column("runs", "lifecycle_events")
    op.drop_column("runs", "started_at")
    for name in ("updated_at", "created_at", "revision"):
        op.drop_column("connections", name)
    op.drop_column("users", "created_at")
    op.drop_table("worker_presence")
