"""Run the agentic generator as an evaluation run that learns on both axes."""

import sqlalchemy as sa
from alembic import op

revision = "0015_agentic_runs"
down_revision = "0014_baseline_only_runs"
branch_labels = None
depends_on = None

ENTITY_ID = sa.String(64).with_variant(sa.Uuid(as_uuid=False), "postgresql")
CARD_AXES = "(axis = 'OR' AND strategy IS NULL) OR (axis = 'AT' AND strategy IS NOT NULL)"
PROMPT_SOURCES = (
    "(axis = 'OR' AND card_id IS NOT NULL AND device IS NOT NULL) "
    "OR (axis = 'AT' AND objective <> '' AND (card_id IS NULL) = (device IS NULL))"
)
OLD_PROMPT_SOURCES = (
    "(axis = 'OR' AND card_id IS NOT NULL AND mechanism IS NOT NULL) "
    "OR (axis = 'AT' AND card_id IS NULL AND mechanism IS NULL AND objective <> '')"
)
OLD_LESSON_SCOPES = "scope IN ('cell', 'risk_mechanism', 'risk')"
OLD_LESSON_COUNTS = "uses >= 0 AND successes >= 0 AND successes <= uses"
AWAITING_RUN = "awaits_run_id IS NULL OR kind = 'agentic'"
ACTIVE_RUN = "status IN ('pending', 'running') OR resumable = {true}"
AWAITING_ACTIVE_RUN = "(" + ACTIVE_RUN + ") AND awaits_run_id IS NULL"
# Rows an agentic run or an attack card wrote, which the old schema cannot hold.
AGENTIC_RUNS = "SELECT run_id FROM runs WHERE kind = 'agentic'"
NEW_PROMPTS = (
    "SELECT prompt_id FROM generator_prompts WHERE run_id IS NOT NULL "
    "OR (axis = 'AT' AND card_id IS NOT NULL)"
)


def upgrade() -> None:
    """Add run kinds, awaited baselines, attack cards, prompt provenance and lessons.

    A pending agentic run that waits for its baseline does not hold the
    owner's single active slot, so the baseline can run first. Every stored
    card and lesson is over-refusal. A stored prompt is attributed to the
    target that answered it, and the lessons' use counts are dropped, since
    the prompts that cite a lesson now record them. The broad per-risk
    lessons are deleted; per-device lessons become group ones.
    """
    op.drop_index("uq_runs_active_owner", table_name="runs")
    with op.batch_alter_table("runs") as batch:
        batch.add_column(
            sa.Column("kind", sa.String(16), nullable=False, server_default="baseline")
        )
        batch.add_column(sa.Column("awaits_run_id", ENTITY_ID, nullable=True))
        batch.create_check_constraint("ck_runs_kind", "kind IN ('baseline', 'agentic')")
        batch.create_foreign_key("fk_runs_awaits", "runs", ["awaits_run_id"], ["run_id"])
        batch.create_check_constraint("ck_runs_awaits", AWAITING_RUN)
    op.create_index("ix_runs_awaits_run_id", "runs", ["awaits_run_id"])
    _active_owner_index(AWAITING_ACTIVE_RUN)
    with op.batch_alter_table("generator_cards") as batch:
        batch.add_column(sa.Column("axis", sa.String(2), nullable=False, server_default="OR"))
        batch.add_column(sa.Column("strategy", sa.String(3), nullable=True))
        batch.add_column(sa.Column("target_model", sa.String(200), nullable=True))
        batch.alter_column("harmless", new_column_name="device", existing_type=sa.String(32))
        batch.create_check_constraint("ck_generator_cards_axis", CARD_AXES)
    op.create_index("ix_generator_cards_target", "generator_cards", ["target_model"])
    _upgrade_prompts()
    _upgrade_lessons()


def _upgrade_prompts() -> None:
    """Attribute prompts to their target and record their run and lessons."""
    with op.batch_alter_table("generator_prompts") as batch:
        batch.drop_constraint("ck_generator_prompts_source", type_="check")
        batch.add_column(sa.Column("target_model", sa.String(200), nullable=True))
        batch.add_column(sa.Column("run_id", ENTITY_ID, nullable=True))
        batch.add_column(
            sa.Column("lesson_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )
        batch.alter_column("mechanism", new_column_name="device", existing_type=sa.String(32))
    op.execute(
        "UPDATE generator_prompts SET target_model = COALESCE("
        "(SELECT MIN(o.target_model) FROM generator_outcomes o "
        "WHERE o.prompt_id = generator_prompts.prompt_id), '')"
    )
    with op.batch_alter_table("generator_prompts") as batch:
        batch.alter_column("target_model", existing_type=sa.String(200), nullable=False)
        batch.create_foreign_key("fk_generator_prompts_run", "runs", ["run_id"], ["run_id"])
        batch.create_check_constraint("ck_generator_prompts_source", PROMPT_SOURCES)
    op.create_index("ix_generator_prompts_target", "generator_prompts", ["target_model", "axis"])
    op.create_index("ix_generator_prompts_run", "generator_prompts", ["run_id"])


def _upgrade_lessons() -> None:
    """Scope lessons to an axis and to the cell or group they were learned in."""
    op.execute("DELETE FROM generator_lessons WHERE scope = 'risk'")
    with op.batch_alter_table("generator_lessons") as batch:
        batch.drop_constraint("ck_generator_lessons_counts", type_="check")
        batch.drop_constraint("ck_generator_lessons_scope", type_="check")
        batch.drop_column("successes")
        batch.drop_column("uses")
        batch.add_column(sa.Column("axis", sa.String(2), nullable=False, server_default="OR"))
    op.execute("UPDATE generator_lessons SET scope = 'group' WHERE scope = 'risk_mechanism'")
    with op.batch_alter_table("generator_lessons") as batch:
        batch.create_check_constraint("ck_generator_lessons_scope", "scope IN ('cell', 'group')")
        batch.create_check_constraint("ck_generator_lessons_axis", "axis IN ('OR', 'AT')")


def downgrade() -> None:
    """Return to over-refusal-only learning and baseline-only runs.

    Agentic runs, the prompts they wrote, attack cards and attack lessons
    cannot be held by the old schema and are deleted.
    """
    op.execute(f"DELETE FROM generator_outcomes WHERE prompt_id IN ({NEW_PROMPTS})")
    op.execute(f"DELETE FROM generator_prompts WHERE prompt_id IN ({NEW_PROMPTS})")
    for table in ("reports", "run_jobs", "run_outcomes"):
        op.execute(f"DELETE FROM {table} WHERE run_id IN ({AGENTIC_RUNS})")
    op.execute("DELETE FROM runs WHERE kind = 'agentic'")
    op.execute("DELETE FROM generator_lessons WHERE axis = 'AT'")
    op.execute("DELETE FROM generator_cards WHERE axis = 'AT'")
    with op.batch_alter_table("generator_lessons") as batch:
        batch.drop_constraint("ck_generator_lessons_axis", type_="check")
        batch.drop_constraint("ck_generator_lessons_scope", type_="check")
        batch.drop_column("axis")
        batch.add_column(sa.Column("uses", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("successes", sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE generator_lessons SET scope = 'risk_mechanism' WHERE scope = 'group'")
    with op.batch_alter_table("generator_lessons") as batch:
        batch.create_check_constraint("ck_generator_lessons_scope", OLD_LESSON_SCOPES)
        batch.create_check_constraint("ck_generator_lessons_counts", OLD_LESSON_COUNTS)
    op.drop_index("ix_generator_prompts_run", table_name="generator_prompts")
    op.drop_index("ix_generator_prompts_target", table_name="generator_prompts")
    with op.batch_alter_table("generator_prompts") as batch:
        batch.drop_constraint("ck_generator_prompts_source", type_="check")
        batch.drop_constraint("fk_generator_prompts_run", type_="foreignkey")
        batch.drop_column("lesson_ids")
        batch.drop_column("run_id")
        batch.drop_column("target_model")
        batch.alter_column("device", new_column_name="mechanism", existing_type=sa.String(32))
    with op.batch_alter_table("generator_prompts") as batch:
        batch.create_check_constraint("ck_generator_prompts_source", OLD_PROMPT_SOURCES)
    op.drop_index("ix_generator_cards_target", table_name="generator_cards")
    with op.batch_alter_table("generator_cards") as batch:
        batch.drop_constraint("ck_generator_cards_axis", type_="check")
        batch.drop_column("target_model")
        batch.drop_column("strategy")
        batch.drop_column("axis")
        batch.alter_column("device", new_column_name="harmless", existing_type=sa.String(32))
    op.drop_index("uq_runs_active_owner", table_name="runs")
    op.drop_index("ix_runs_awaits_run_id", table_name="runs")
    with op.batch_alter_table("runs") as batch:
        batch.drop_constraint("ck_runs_awaits", type_="check")
        batch.drop_constraint("fk_runs_awaits", type_="foreignkey")
        batch.drop_constraint("ck_runs_kind", type_="check")
        batch.drop_column("awaits_run_id")
        batch.drop_column("kind")
    _active_owner_index(ACTIVE_RUN)


def _active_owner_index(condition: str) -> None:
    """Allow each owner one active run, under the given partial condition."""
    op.create_index(
        "uq_runs_active_owner",
        "runs",
        ["owner_id"],
        unique=True,
        postgresql_where=sa.text(condition.format(true="true")),
        sqlite_where=sa.text(condition.format(true="1")),
    )
