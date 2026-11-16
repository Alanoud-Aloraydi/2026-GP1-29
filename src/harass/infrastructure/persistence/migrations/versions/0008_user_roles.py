"""Add the account role, defaulting every existing account to a plain user."""

import sqlalchemy as sa
from alembic import op

revision = "0008_user_roles"
down_revision = "0007_account_actions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Grant no extra access to accounts that already exist."""
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "role",
                sa.String(16),
                nullable=False,
                server_default="user",
            )
        )
        batch.create_check_constraint(
            "ck_users_role", "role IN ('user', 'admin')"
        )


def downgrade() -> None:
    """Drop the role; administrators become plain users again."""
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_users_role", type_="check")
        batch.drop_column("role")
