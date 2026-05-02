"""add moderation_notes and sla_due_at columns

Revision ID: a1b2c3d4e5f6
Revises: 5649512f749d
Create Date: 2026-04-29 15:47:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '5649512f749d'
branch_labels = None
depends_on = None


def upgrade():
    # Add moderation_notes column to organisations table
    op.add_column('organisations', sa.Column('moderation_notes', sa.Text(), nullable=True))
    
    # Add sla_due_at column to content_submissions table
    op.add_column('content_submissions', sa.Column('sla_due_at', sa.DateTime(), nullable=True))
    
    # Add moderation_notes column to events table
    op.add_column('events', sa.Column('moderation_notes', sa.Text(), nullable=True))


def downgrade():
    # Remove moderation_notes column from organisations table
    op.drop_column('organisations', 'moderation_notes')
    
    # Remove sla_due_at column from content_submissions table
    op.drop_column('content_submissions', 'sla_due_at')
    
    # Remove moderation_notes column from events table
    op.drop_column('events', 'moderation_notes')
