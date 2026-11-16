"""Store published judge benchmark reports for administrators."""

import sqlalchemy as sa
from alembic import op

revision = "0009_judge_benchmark_reports"
down_revision = "0008_user_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the report table with its integrity constraints."""
    identifier = sa.String(64).with_variant(
        sa.Uuid(as_uuid=False), "postgresql"
    )
    op.create_table(
        "judge_benchmark_reports",
        sa.Column("report_id", identifier, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("judge_model", sa.String(200), nullable=False),
        sa.Column("quantization", sa.String(64), nullable=True),
        sa.Column("split", sa.String(8), nullable=False),
        sa.Column("trials", sa.Integer(), nullable=False),
        sa.Column("cases", sa.Integer(), nullable=False),
        sa.Column("rubric_fingerprint", sa.String(32), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "split IN ('dev', 'test', 'all')",
            name="ck_judge_benchmark_reports_split",
        ),
        sa.CheckConstraint(
            "trials >= 1", name="ck_judge_benchmark_reports_trials"
        ),
        sa.CheckConstraint(
            "cases >= 1", name="ck_judge_benchmark_reports_cases"
        ),
    )
    op.create_index(
        "ix_judge_benchmark_reports_created_at",
        "judge_benchmark_reports",
        ["created_at"],
    )


def downgrade() -> None:
    """Remove the reports; they can be published again from their files."""
    op.drop_index(
        "ix_judge_benchmark_reports_created_at",
        table_name="judge_benchmark_reports",
    )
    op.drop_table("judge_benchmark_reports")
