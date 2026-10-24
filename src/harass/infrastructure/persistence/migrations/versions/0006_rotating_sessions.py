"""Add bounded refresh-token rotation to revocable account sessions."""

import sqlalchemy as sa
from alembic import op

revision = "0006_rotating_sessions"
down_revision = "0005_integrity_uuid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Preserve existing sessions while adding nullable refresh credentials."""
    op.add_column(
        "authentication_sessions",
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "authentication_sessions",
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "authentication_sessions", sa.Column("refresh_hash", sa.String(64))
    )
    op.add_column(
        "authentication_sessions",
        sa.Column(
            "used_refresh_hashes",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    """Remove refresh metadata while retaining accounts and evaluations."""
    for column in (
        "used_refresh_hashes",
        "refresh_hash",
        "refresh_expires_at",
        "created_at",
    ):
        op.drop_column("authentication_sessions", column)
