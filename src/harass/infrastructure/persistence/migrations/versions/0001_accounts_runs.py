"""Create accounts, connections and evaluation storage."""

import sqlalchemy as sa
from alembic import op

revision: str = "0001_accounts_runs"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Apply this schema revision."""
    op.create_table(
        "connections",
        sa.Column("connection_id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("connection_id"),
    )
    op.create_index(op.f("ix_connections_owner_id"), "connections", ["owner_id"], unique=False)
    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=64), nullable=False),
        sa.Column("target_model", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(op.f("ix_runs_owner_id"), "runs", ["owner_id"], unique=False)
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("full_name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_table(
        "authentication_sessions",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
        ),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index(
        op.f("ix_authentication_sessions_expires_at"),
        "authentication_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_authentication_sessions_user_id"),
        "authentication_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "reports",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id"),
    )


def downgrade() -> None:
    """Reverse this schema revision."""
    op.drop_table("reports")
    op.drop_index(op.f("ix_authentication_sessions_user_id"), table_name="authentication_sessions")
    op.drop_index(
        op.f("ix_authentication_sessions_expires_at"), table_name="authentication_sessions"
    )
    op.drop_table("authentication_sessions")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    op.drop_index(op.f("ix_runs_owner_id"), table_name="runs")
    op.drop_table("runs")
    op.drop_index(op.f("ix_connections_owner_id"), table_name="connections")
    op.drop_table("connections")
