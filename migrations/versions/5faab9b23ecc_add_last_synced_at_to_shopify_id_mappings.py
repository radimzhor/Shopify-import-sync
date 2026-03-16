"""add last_synced_at to shopify_id_mappings

Revision ID: 5faab9b23ecc
Revises: b9e3e1e52c34
Create Date: 2026-03-16 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5faab9b23ecc'
down_revision = 'b9e3e1e52c34'
branch_labels = None
depends_on = None


def upgrade():
    # Add last_synced_at column to shopify_id_mappings
    with op.batch_alter_table('shopify_id_mappings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_synced_at', sa.DateTime(), nullable=True))
        batch_op.create_index(batch_op.f('ix_shopify_id_mappings_last_synced_at'), ['last_synced_at'], unique=False)


def downgrade():
    # Remove last_synced_at column
    with op.batch_alter_table('shopify_id_mappings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_shopify_id_mappings_last_synced_at'))
        batch_op.drop_column('last_synced_at')
