"""Add event_type column to events table

Revision ID: d9a2a9f82ed4
Revises: 489d61e4ca9b
Create Date: 2026-04-24 18:12:33.724749

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd9a2a9f82ed4'
down_revision = '489d61e4ca9b'
branch_labels = None
depends_on = None


def upgrade():
    # Add event_type column to events table
    op.add_column('events', sa.Column('event_type', sa.String(20), server_default='ticketed', nullable=True))


def downgrade():
    # Remove event_type column from events table
    op.drop_column('events', 'event_type')