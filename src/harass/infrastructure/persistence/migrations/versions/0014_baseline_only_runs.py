"""Keep one baseline attempt per case: drop template attempts and the archive."""

from collections import Counter, defaultdict
from typing import Any

import sqlalchemy as sa
from alembic import context, op

revision = "0014_baseline_only_runs"
down_revision = "0013_generation_attacks"
branch_labels = None
depends_on = None

REPORT_FORMAT_VERSION = 4
PROGRESS = "total_cases >= 0 AND completed_cases >= 0 AND completed_cases <= total_cases"
# Report keys that described template recipes, the Thompson controller or the
# split between generated and original attempts.
REMOVED_REPORT_KEYS = frozenset(
    {
        "variants",
        "include_baseline",
        "evaluation_mode",
        "run_type",
        "attempt_budget",
        "controller_seed",
        "metric_scope",
        "baseline_metrics",
        "primary_metrics",
        "primary_metric_scope",
        "strategy_breakdown_scope",
        "variant_selection",
        "adaptive",
        "coverage_count_scope",
    }
)
ENTITY_ID = sa.String(64).with_variant(sa.Uuid(as_uuid=False), "postgresql")

reports = sa.table("reports", sa.column("run_id", ENTITY_ID), sa.column("document", sa.JSON))
run_outcomes = sa.table(
    "run_outcomes", sa.column("run_id", ENTITY_ID), sa.column("metric_document", sa.JSON)
)


def upgrade() -> None:
    """Delete template attempts, rewrite reports and drop what only they used.

    Each run keeps its original-request attempts, and its stored report is
    rebuilt from them. Offline SQL rendering cannot read rows, so it leaves
    the stored report documents unchanged.
    """
    op.execute("DELETE FROM run_outcomes WHERE attempt_number > 0")
    if not context.is_offline_mode():
        _rewrite_reports()
    op.drop_index(op.f("ix_prompt_findings_run_id"), table_name="prompt_findings")
    op.drop_index(op.f("ix_prompt_findings_content_sha256"), table_name="prompt_findings")
    op.drop_table("prompt_findings")
    op.drop_table("generated_prompts")
    with op.batch_alter_table("runs") as batch:
        batch.drop_constraint("ck_runs_progress", type_="check")
        batch.drop_column("completed_attempts")
        batch.create_check_constraint("ck_runs_progress", PROGRESS)
    _replace_outcome_key(["run_id", "case_index"], drop="attempt_number")


def downgrade() -> None:
    """Restore the attempt columns and the empty archive tables.

    Deleted template attempts and archived findings cannot be restored, and
    reports keep the format they were rewritten to.
    """
    _replace_outcome_key(["run_id", "case_index", "attempt_number"], add="attempt_number")
    with op.batch_alter_table("runs") as batch:
        batch.drop_constraint("ck_runs_progress", type_="check")
        batch.add_column(
            sa.Column("completed_attempts", sa.Integer(), server_default="0", nullable=False)
        )
    op.execute("UPDATE runs SET completed_attempts = completed_cases")
    with op.batch_alter_table("runs") as batch:
        batch.create_check_constraint("ck_runs_progress", f"{PROGRESS} AND completed_attempts >= 0")
    op.create_table(
        "generated_prompts",
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("content_sha256"),
    )
    op.create_table(
        "prompt_findings",
        sa.Column("finding_id", ENTITY_ID, nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("run_id", ENTITY_ID, nullable=False),
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
            name="prompt_findings_content_sha256_fkey",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.run_id"], name="prompt_findings_run_id_fkey"),
        sa.PrimaryKeyConstraint("finding_id"),
        sa.UniqueConstraint("run_id", "case_id", "variant_id", "attempt_number"),
    )
    op.create_index(
        op.f("ix_prompt_findings_content_sha256"), "prompt_findings", ["content_sha256"]
    )
    op.create_index(op.f("ix_prompt_findings_run_id"), "prompt_findings", ["run_id"])


def _replace_outcome_key(
    columns: list[str], *, drop: str | None = None, add: str | None = None
) -> None:
    """Rebuild the run_outcomes primary key around the given columns.

    PostgreSQL named the key ``run_outcomes_pkey`` when 0003 created it;
    SQLite has no named keys, so its table is recreated instead.
    """
    if op.get_bind().dialect.name == "postgresql" or context.is_offline_mode():
        op.drop_constraint("run_outcomes_pkey", "run_outcomes", type_="primary")
        if drop:
            op.drop_column("run_outcomes", drop)
        if add:
            op.add_column(
                "run_outcomes", sa.Column(add, sa.Integer(), server_default="0", nullable=False)
            )
        op.create_primary_key("run_outcomes_pkey", "run_outcomes", columns)
        return
    with op.batch_alter_table("run_outcomes", recreate="always") as batch:
        if drop:
            batch.drop_column(drop)
        if add:
            batch.add_column(
                sa.Column(add, sa.Integer(), server_default="0", nullable=False, primary_key=True)
            )
        batch.create_primary_key("run_outcomes_pkey", columns)


def _rewrite_reports() -> None:
    """Rebuild every stored report from its run's remaining attempts.

    Reports before format 4 kept the original-request metrics separately as
    ``baseline_metrics``; those become the report's metrics. Reads one run's
    attempts at a time, so memory stays bounded by the largest run.
    """
    connection = op.get_bind()
    for run_id, document in connection.execute(sa.select(reports.c.run_id, reports.c.document)):
        rows = [
            row
            for (row,) in connection.execute(
                sa.select(run_outcomes.c.metric_document).where(run_outcomes.c.run_id == run_id)
            )
        ]
        connection.execute(
            reports.update()
            .where(reports.c.run_id == run_id)
            .values(document=_baseline_report(document, rows))
        )


def _baseline_report(document: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the format-4 report of one run's original-request attempts."""
    metrics = dict(document.get("baseline_metrics") or document["metrics"])
    metrics.pop("discrimination_gap_by_variant", None)
    for name in ("adversarial_breakdowns", "over_refusal_breakdowns"):
        metrics[name] = {
            dimension: groups
            for dimension, groups in (metrics.get(name) or {}).items()
            if dimension != "variant"
        }
    rebuilt = {key: value for key, value in document.items() if key not in REMOVED_REPORT_KEYS}
    rebuilt.update(
        format_version=REPORT_FORMAT_VERSION,
        metrics=metrics,
        outcomes_count=len(rows),
        coverage=_coverage(rows),
        response_categories=_response_categories(rows),
    )
    return rebuilt


def _is_scored(row: dict[str, Any]) -> bool:
    """Mirror CaseOutcome.is_scored on a stored attempt document."""
    if row.get("error") is not None or row.get("response_category") is None:
        return False
    return row["axis"] == "OR" or row.get("attack_succeeded") is not None


def _coverage(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Count sent, unscored, unclear and rule-suspected attempts per axis."""
    coverage: dict[str, dict[str, int]] = {}
    for row in rows:
        counts = coverage.setdefault(
            row["axis"], {"submitted": 0, "unscored": 0, "unclear": 0, "suspected_unclear": 0}
        )
        counts["submitted"] += 1
        counts["unscored"] += not _is_scored(row)
        counts["unclear"] += row.get("error") is None and row.get("response_category") == "UNC"
        counts["suspected_unclear"] += row.get("comprehension_signal") is not None
    return coverage


def _response_categories(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Count scored responses by category for each axis."""
    counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        if _is_scored(row):
            counts[row["axis"]][row["response_category"]] += 1
    return {axis: dict(categories) for axis, categories in counts.items()}
