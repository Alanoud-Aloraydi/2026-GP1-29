"""Drop the prompt-generator benchmark reports, which the site no longer shows."""

import sqlalchemy as sa
from alembic import op

revision = "0011_drop_generator_reports"
down_revision = "0010_generator_benchmark_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Remove the report table and its index; the source files stay outside the project."""
    op.drop_index(
        "ix_generator_benchmark_reports_created_at", table_name="generator_benchmark_reports"
    )
    op.drop_table("generator_benchmark_reports")


def downgrade() -> None:
    """Recreate the empty table as revision 0010 defined it."""
    identifier = sa.String(64).with_variant(sa.Uuid(as_uuid=False), "postgresql")
    op.create_table(
        "generator_benchmark_reports",
        sa.Column("report_id", identifier, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generator_model", sa.String(200), nullable=False),
        sa.Column("axis", sa.String(2), nullable=False),
        sa.Column("cases", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.CheckConstraint("axis IN ('OR', 'AT')", name="ck_generator_benchmark_reports_axis"),
        sa.CheckConstraint("cases >= 1", name="ck_generator_benchmark_reports_cases"),
    )
    op.create_index(
        "ix_generator_benchmark_reports_created_at", "generator_benchmark_reports", ["created_at"]
    )
