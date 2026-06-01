"""Add analytics_page_views aggregate table

Revision ID: afcon360_analytics_001
Revises: 5d751ad7bf6f
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa

revision = 'afcon360_analytics_001'
down_revision = '5d751ad7bf6f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'analytics_page_views',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('module', sa.String(length=64), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_type', sa.String(length=16), nullable=False),
        sa.Column('view_count', sa.Integer(), nullable=False, default=0),
        sa.Column('unique_users', sa.Integer(), nullable=False, default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_apv_module_period', 'analytics_page_views', ['module', 'period_start', 'period_type'])
    op.create_index('ix_apv_period_start', 'analytics_page_views', ['period_start'])
    op.create_unique_constraint('uq_apv_module_period', 'analytics_page_views', ['module', 'period_start', 'period_type'])


def downgrade():
    op.drop_constraint('uq_apv_module_period', 'analytics_page_views', type_='unique')
    op.drop_index('ix_apv_period_start', table_name='analytics_page_views')
    op.drop_index('ix_apv_module_period', table_name='analytics_page_views')
    op.drop_table('analytics_page_views')
