"""${message}."""

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | None = ${repr(branch_labels)}
depends_on: str | None = ${repr(depends_on)}


def upgrade() -> None:
    """Apply this schema revision."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Reverse this schema revision."""
    ${downgrades if downgrades else "pass"}
