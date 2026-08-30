"""add_booking_flow_type

Revision ID: 20260830_1420
Revises: 8a0deccce6f6
Create Date: 2026-08-30 14:20:37.054145

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260830_1420'
down_revision = '8a0deccce6f6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('accommodation_bookings', sa.Column('booking_flow_type', sa.String(length=30), nullable=True))


def downgrade():
    op.drop_column('accommodation_bookings', 'booking_flow_type')
