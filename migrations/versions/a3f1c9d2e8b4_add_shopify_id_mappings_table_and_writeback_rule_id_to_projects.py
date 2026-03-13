"""add shopify_id_mappings table and writeback_rule_id to projects

Revision ID: a3f1c9d2e8b4
Revises: 7651c38f05e2
Create Date: 2026-03-13 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a3f1c9d2e8b4'
down_revision = '7651c38f05e2'
branch_labels = None
depends_on = None


def upgrade():
    # Create shopify_id_mappings table
    op.create_table(
        'shopify_id_mappings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('sku', sa.String(length=200), nullable=False),
        sa.Column('shopify_product_id', sa.String(length=50), nullable=False),
        sa.Column('shopify_variant_id', sa.String(length=50), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'sku', name='uq_shopify_id_mapping_project_sku'),
    )
    with op.batch_alter_table('shopify_id_mappings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_shopify_id_mappings_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_shopify_id_mappings_sku'), ['sku'], unique=False)

    # Add writeback rule ID column to projects
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.add_column(sa.Column('shopify_writeback_rule_id', sa.String(length=50), nullable=True))


def downgrade():
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_column('shopify_writeback_rule_id')

    with op.batch_alter_table('shopify_id_mappings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_shopify_id_mappings_sku'))
        batch_op.drop_index(batch_op.f('ix_shopify_id_mappings_project_id'))

    op.drop_table('shopify_id_mappings')
