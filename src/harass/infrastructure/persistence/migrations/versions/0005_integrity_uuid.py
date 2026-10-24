"""Native PostgreSQL entity identifiers and ownership integrity."""

from typing import Any

import sqlalchemy as sa
from alembic import context, op

revision = "0005_integrity_uuid"
down_revision = "0004_execution_controls"
branch_labels = None
depends_on = None

IDENTIFIERS = {
    "users": ("user_id",),
    "authentication_sessions": ("session_id", "user_id"),
    "connections": ("connection_id", "owner_id"),
    "runs": ("run_id", "owner_id", "connection_id"),
    "reports": ("run_id",),
    "prompt_findings": ("finding_id", "run_id"),
    "run_jobs": ("run_id",),
    "run_outcomes": ("run_id",),
}


def _identifiers(native: bool) -> None:
    """Convert dependent identifier columns while preserving UUIDs."""
    if op.get_bind().dialect.name != "postgresql":
        return
    constraints: list[
        tuple[str, str, list[str], str, list[str], dict[str, Any]]
    ] = []
    if context.is_offline_mode():
        for table, column, parent, parent_column in (
            ("authentication_sessions", "user_id", "users", "user_id"),
            ("reports", "run_id", "runs", "run_id"),
            ("prompt_findings", "run_id", "runs", "run_id"),
            ("run_jobs", "run_id", "runs", "run_id"),
            ("run_outcomes", "run_id", "runs", "run_id"),
        ):
            options: dict[str, Any] = (
                {"ondelete": "CASCADE"} if table == "reports" else {}
            )
            constraints.append(
                (
                    table,
                    f"{table}_{column}_fkey",
                    [column],
                    parent,
                    [parent_column],
                    options,
                )
            )
    else:
        inspector = sa.inspect(op.get_bind())
        for table, columns in IDENTIFIERS.items():
            for foreign_key in inspector.get_foreign_keys(table):
                if set(foreign_key["constrained_columns"]) & set(columns):
                    name = foreign_key["name"]
                    if name is None:
                        raise RuntimeError(
                            "PostgreSQL identifier foreign keys must be named."
                        )
                    constraints.append(
                        (
                            table,
                            name,
                            foreign_key["constrained_columns"],
                            foreign_key["referred_table"],
                            foreign_key["referred_columns"],
                            foreign_key.get("options", {}),
                        )
                    )
    for table, name, _, _, _, _ in constraints:
        op.drop_constraint(name, table, type_="foreignkey")
    for table, columns in IDENTIFIERS.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                type_=sa.Uuid(as_uuid=False) if native else sa.String(64),
                postgresql_using=f'"{column}"::'
                + ("uuid" if native else "text"),
            )
    for (
        table,
        name,
        local_columns,
        parent,
        parent_columns,
        foreign_options,
    ) in constraints:
        op.create_foreign_key(
            name,
            table,
            parent,
            local_columns,
            parent_columns,
            **foreign_options,
        )


def upgrade() -> None:
    """Validate legacy ownership and apply identifier constraints."""
    _identifiers(True)
    with op.batch_alter_table("connections") as batch:
        batch.create_unique_constraint(
            "uq_connections_identity_owner", ["connection_id", "owner_id"]
        )
        batch.create_foreign_key(
            "fk_connections_owner", "users", ["owner_id"], ["user_id"]
        )
        batch.create_check_constraint(
            "ck_connections_status",
            "status IN ('not_tested', 'connected', 'failed')",
        )
        batch.create_check_constraint(
            "ck_connections_revision", "revision >= 0"
        )
    with op.batch_alter_table("runs") as batch:
        batch.create_foreign_key(
            "fk_runs_owner", "users", ["owner_id"], ["user_id"]
        )
        batch.create_foreign_key(
            "fk_runs_connection_owner",
            "connections",
            ["connection_id", "owner_id"],
            ["connection_id", "owner_id"],
        )
        batch.create_check_constraint(
            "ck_runs_status",
            (
                "status IN ('pending', 'running', 'completed', "
                "'failed', 'cancelled')"
            ),
        )
        batch.create_check_constraint(
            "ck_runs_progress",
            (
                "total_cases >= 0 AND completed_cases >= 0 AND "
                "completed_cases <= total_cases AND "
                "completed_attempts >= 0"
            ),
        )


def downgrade() -> None:
    """Remove new constraints before reverting identifier storage."""
    with op.batch_alter_table("runs") as batch:
        for name, kind in (
            ("ck_runs_progress", "check"),
            ("ck_runs_status", "check"),
            ("fk_runs_connection_owner", "foreignkey"),
            ("fk_runs_owner", "foreignkey"),
        ):
            batch.drop_constraint(name, type_=kind)
    with op.batch_alter_table("connections") as batch:
        for name, kind in (
            ("ck_connections_revision", "check"),
            ("ck_connections_status", "check"),
            ("fk_connections_owner", "foreignkey"),
            ("uq_connections_identity_owner", "unique"),
        ):
            batch.drop_constraint(name, type_=kind)
    _identifiers(False)
