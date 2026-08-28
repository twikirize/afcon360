"""accommodation_booking_mode_db_default

Revision ID: 20260828_booking_mode_default
Revises: db8cd686f423
Create Date: 2026-08-28

"""
from alembic import op
import sqlalchemy as sa

revision = '20260828_booking_mode_default'
down_revision = 'db8cd686f423'
branch_labels = None
depends_on = None


def upgrade():
    # Add server_default to existing booking_mode column
    op.alter_column(
        'accommodation_properties',
        'booking_mode',
        existing_type=sa.String(20),
        server_default='instant',
        existing_nullable=False
    )


def downgrade():
    # Remove server_default
    op.alter_column(
        'accommodation_properties',
        'booking_mode',
        existing_type=sa.String(20),
        server_default=None,
        existing_nullable=False
    )