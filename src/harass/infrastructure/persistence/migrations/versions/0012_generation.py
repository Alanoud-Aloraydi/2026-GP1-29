"""Store the prompt generator's cards, prompts, outcomes and lessons."""

import sqlalchemy as sa
from alembic import op

revision = "0012_generation"
down_revision = "0011_drop_generator_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the generator tables with their integrity constraints."""
    identifier = sa.String(64).with_variant(sa.Uuid(as_uuid=False), "postgresql")
    op.create_table(
        "generator_cards",
        sa.Column("card_id", sa.String(128), primary_key=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("domain", sa.String(3), nullable=False),
        sa.Column("risk", sa.String(3), nullable=False),
        sa.Column("form", sa.String(16), nullable=False),
        sa.Column("target", sa.String(16), nullable=False),
        sa.Column("harmless", sa.String(32), nullable=False),
        sa.Column("shape", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source IN ('baseline', 'generated')", name="ck_generator_cards_source"),
    )
    op.create_table(
        "generator_prompts",
        sa.Column("prompt_id", identifier, primary_key=True),
        sa.Column("case_id", sa.String(128), nullable=False),
        sa.Column("cell_key", sa.String(32), nullable=False),
        sa.Column("mechanism", sa.String(32), nullable=False),
        sa.Column("card_id", sa.String(128), nullable=False),
        sa.Column("round_index", sa.Integer(), nullable=False),
        sa.Column("written_text", sa.Text(), nullable=False),
        sa.Column("sent_text", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("reviewer_passed", sa.Boolean(), nullable=False),
        sa.Column("reviewer_notes", sa.JSON(), nullable=False),
        sa.Column("intent_safe", sa.Boolean(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["card_id"], ["generator_cards.card_id"], name="fk_generator_prompts_card"
        ),
        sa.CheckConstraint("round_index >= 0", name="ck_generator_prompts_round"),
        sa.CheckConstraint("attempts >= 1", name="ck_generator_prompts_attempts"),
    )
    op.create_index("ix_generator_prompts_round", "generator_prompts", ["round_index"])
    op.create_index("ix_generator_prompts_cell", "generator_prompts", ["cell_key"])
    op.create_table(
        "generator_outcomes",
        sa.Column("prompt_id", identifier, primary_key=True),
        sa.Column("target_model", sa.String(200), primary_key=True),
        sa.Column("response_category", sa.String(3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["prompt_id"], ["generator_prompts.prompt_id"], name="fk_generator_outcomes_prompt"
        ),
        sa.CheckConstraint(
            "response_category IN ('FUL', 'PRF', 'REF', 'UNC')",
            name="ck_generator_outcomes_category",
        ),
    )
    op.create_table(
        "generator_lessons",
        sa.Column("lesson_id", sa.String(200), primary_key=True),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("scope_key", sa.String(64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("target_model", sa.String(200), nullable=False),
        sa.Column("uses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("successes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scope IN ('cell', 'risk_mechanism', 'risk')", name="ck_generator_lessons_scope"
        ),
        sa.CheckConstraint(
            "uses >= 0 AND successes >= 0 AND successes <= uses", name="ck_generator_lessons_counts"
        ),
    )
    op.create_index(
        "ix_generator_lessons_scope", "generator_lessons", ["scope", "scope_key", "target_model"]
    )


def downgrade() -> None:
    """Remove the generator tables, outcomes before the prompts they cite."""
    op.drop_index("ix_generator_lessons_scope", table_name="generator_lessons")
    op.drop_table("generator_lessons")
    op.drop_table("generator_outcomes")
    op.drop_index("ix_generator_prompts_cell", table_name="generator_prompts")
    op.drop_index("ix_generator_prompts_round", table_name="generator_prompts")
    op.drop_table("generator_prompts")
    op.drop_table("generator_cards")
