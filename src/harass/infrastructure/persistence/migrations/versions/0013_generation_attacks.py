"""Store attack prompts beside over-refusal ones, with every stage and the reply."""

import sqlalchemy as sa
from alembic import op

revision = "0013_generation_attacks"
down_revision = "0012_generation"
branch_labels = None
depends_on = None

PROMPT_SOURCES = (
    "(axis = 'OR' AND card_id IS NOT NULL AND mechanism IS NOT NULL) "
    "OR (axis = 'AT' AND card_id IS NULL AND mechanism IS NULL AND objective <> '')"
)


def upgrade() -> None:
    """Add the axis, the localized text, the adapter and the judged reply.

    Every stored prompt is over-refusal and was sent untransformed, so its
    localized text is its sent text.
    """
    with op.batch_alter_table("generator_prompts") as batch:
        batch.add_column(sa.Column("axis", sa.String(2), nullable=False, server_default="OR"))
        batch.add_column(sa.Column("localized_text", sa.Text(), nullable=True))
        batch.add_column(sa.Column("objective", sa.Text(), nullable=False, server_default=""))
        batch.add_column(
            sa.Column("transform_names", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )
        batch.alter_column("mechanism", existing_type=sa.String(32), nullable=True)
        batch.alter_column("card_id", existing_type=sa.String(128), nullable=True)
    op.execute("UPDATE generator_prompts SET localized_text = sent_text")
    with op.batch_alter_table("generator_prompts") as batch:
        batch.alter_column("localized_text", existing_type=sa.Text(), nullable=False)
        batch.create_check_constraint("ck_generator_prompts_axis", "axis IN ('OR', 'AT')")
        batch.create_check_constraint("ck_generator_prompts_source", PROMPT_SOURCES)
    op.create_index("ix_generator_prompts_axis", "generator_prompts", ["axis"])
    with op.batch_alter_table("generator_outcomes") as batch:
        batch.add_column(sa.Column("attack_succeeded", sa.Boolean(), nullable=True))
        for name in ("response_text", "category_rationale", "attack_rationale"):
            batch.add_column(sa.Column(name, sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    """Drop the attack columns; stored attacks and their outcomes go with them."""
    op.execute(
        "DELETE FROM generator_outcomes WHERE prompt_id IN "
        "(SELECT prompt_id FROM generator_prompts WHERE axis = 'AT')"
    )
    op.execute("DELETE FROM generator_prompts WHERE axis = 'AT'")
    with op.batch_alter_table("generator_outcomes") as batch:
        for name in ("attack_rationale", "category_rationale", "response_text", "attack_succeeded"):
            batch.drop_column(name)
    op.drop_index("ix_generator_prompts_axis", table_name="generator_prompts")
    with op.batch_alter_table("generator_prompts") as batch:
        batch.drop_constraint("ck_generator_prompts_source", type_="check")
        batch.drop_constraint("ck_generator_prompts_axis", type_="check")
        batch.alter_column("card_id", existing_type=sa.String(128), nullable=False)
        batch.alter_column("mechanism", existing_type=sa.String(32), nullable=False)
        for name in ("transform_names", "objective", "localized_text", "axis"):
            batch.drop_column(name)
