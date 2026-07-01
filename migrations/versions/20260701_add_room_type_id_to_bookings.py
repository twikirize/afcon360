"""Add room_type_id to accommodation_bookings

Revision ID: 20260701a
Revises: 1d30290f4f67
Create Date: 2026-07-01 11:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260701a'
down_revision = '1d30290f4f67'
branch_labels = None
depends_on = None


def upgrade():
    # Add room_type_id column to accommodation_bookings
    op.add_column('accommodation_bookings', sa.Column('room_type_id', sa.BigInteger(), nullable=True))
    op.create_index('ix_accommodation_bookings_room_type_id', 'accommodation_bookings', ['room_type_id'])
    op.create_foreign_key('fk_booking_room_type', 'accommodation_bookings', 'accommodation_room_types', ['room_type_id'], ['id'], ondelete='RESTRICT')


def downgrade():
    # Remove room_type_id column
    op.drop_constraint('fk_booking_room_type', 'accommodation_bookings', type_='foreignkey')
    op.drop_index('ix_accommodation_bookings_room_type_id', table_name='accommodation_bookings')
    op.drop_column('accommodation_bookings', 'room_type_id')