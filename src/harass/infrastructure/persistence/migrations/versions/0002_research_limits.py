"""Add internal research archive and shared request limits."""

import sqlalchemy as sa
from alembic import op

revision: str = "0002_research_limits"
down_revision: str | None = "0001_accounts_runs"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Apply this schema revision."""
    op.create_table(
        "generated_prompts",
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("content_sha256"),
    )
    op.create_table(
        "request_limits",
        sa.Column("bucket_key", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.Integer(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("bucket_key"),
    )
    op.create_table(
        "prompt_findings",
        sa.Column("finding_id", sa.String(length=64), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=128), nullable=False),
        sa.Column("variant_id", sa.Text(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("axis", sa.String(length=2), nullable=False),
        sa.Column("target_model", sa.Text(), nullable=False),
        sa.Column("target_endpoint", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["content_sha256"],
            ["generated_prompts.content_sha256"],
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.run_id"],
        ),
        sa.PrimaryKeyConstraint("finding_id"),
        sa.UniqueConstraint("run_id", "case_id", "variant_id", "attempt_number"),
    )
    op.create_index("ix_request_limits_window_start", "request_limits", ["window_start"])
    op.create_index(
        op.f("ix_prompt_findings_content_sha256"),
        "prompt_findings",
        ["content_sha256"],
        unique=False,
    )
    op.create_index(op.f("ix_prompt_findings_run_id"), "prompt_findings", ["run_id"], unique=False)


def downgrade() -> None:
    """Reverse this schema revision."""
    op.drop_index(op.f("ix_prompt_findings_run_id"), table_name="prompt_findings")
    op.drop_index(op.f("ix_prompt_findings_content_sha256"), table_name="prompt_findings")
    op.drop_table("prompt_findings")
    op.drop_index("ix_request_limits_window_start", table_name="request_limits")
    op.drop_table("request_limits")
    op.drop_table("generated_prompts")
