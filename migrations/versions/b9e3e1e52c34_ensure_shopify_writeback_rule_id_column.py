"""ensure shopify_writeback_rule_id column exists on projects

Revision ID: b9e3e1e52c34
Revises: a3f1c9d2e8b4
Create Date: 2026-03-13 20:55:00.000000
"""

from alembic import op
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision = "b9e3e1e52c34"
down_revision = "a3f1c9d2e8b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Ensure the projects.shopify_writeback_rule_id column exists.
    Uses IF NOT EXISTS so it is safe and idempotent across environments.
    """
    op.execute(
        "ALTER TABLE projects "
        "ADD COLUMN IF NOT EXISTS shopify_writeback_rule_id VARCHAR(50);"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE projects "
        "DROP COLUMN IF EXISTS shopify_writeback_rule_id;"
    )

