"""compatibility migration: organizer_profiles already exists in baseline

Revision ID: 23a2748dc5d1
Revises: 8a0deccce6f6

The root migration 8a0deccce6f6 builds the complete SQLAlchemy metadata,
which already includes organizer_profiles. This historical migration
originally attempted to create the same table a second time.

It is intentionally retained as a no-op to preserve Alembic history.
"""

from alembic import op


revision = "23a2748dc5d1"
down_revision = "8a0deccce6f6"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
