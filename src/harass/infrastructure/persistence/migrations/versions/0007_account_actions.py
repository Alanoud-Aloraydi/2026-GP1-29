"""Add optional email verification and hashed single-use account actions."""

import sqlalchemy as sa
from alembic import op

revision = "0007_account_actions"
down_revision = "0006_rotating_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Preserve accounts while adding inactive account-email capabilities."""
    identifier = sa.String(64).with_variant(
        sa.Uuid(as_uuid=False), "postgresql"
    )
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_table(
        "account_actions",
        sa.Column("action_id", identifier, primary_key=True),
        sa.Column(
            "user_id",
            identifier,
            sa.ForeignKey("users.user_id"),
            nullable=False,
        ),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("credential_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "purpose IN ('verify_email', 'reset_password')",
            name="ck_account_action_purpose",
        ),
    )
    op.create_index(
        "ix_account_actions_user_id", "account_actions", ["user_id"]
    )


def downgrade() -> None:
    """Remove action metadata while retaining users and evaluation records."""
    op.drop_index("ix_account_actions_user_id", table_name="account_actions")
    op.drop_table("account_actions")
    op.drop_column("users", "email_verified")
