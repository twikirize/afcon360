"""Add room_types and inventory_blocks tables for multi-unit property support

Revision ID: 20260701_add_room_types
Revises: a976e4599bfe
Create Date: 2026-07-01

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260701_add_room_types'
down_revision = 'a976e4599bfe'
branch_labels = None
depends_on = None


def upgrade():
    # Check if tables already exist
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # Create accommodation_room_types table
    if 'accommodation_room_types' not in existing_tables:
        op.create_table(
            'accommodation_room_types',
            sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column('public_id', sa.String(64), nullable=False),
            sa.Column('property_id', sa.BigInteger(), sa.ForeignKey('accommodation_properties.id', ondelete='CASCADE'), nullable=False),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('max_guests', sa.Integer(), nullable=False, server_default='2'),
            sa.Column('bedrooms', sa.Integer(), nullable=True, server_default='1'),
            sa.Column('beds', sa.Integer(), nullable=True, server_default='1'),
            sa.Column('bathrooms', sa.Float(), nullable=True, server_default='1.0'),
            sa.Column('base_price_per_night', sa.Numeric(10, 2), nullable=False),
            sa.Column('currency', sa.String(3), nullable=False, server_default='USD'),
            sa.Column('cleaning_fee', sa.Numeric(10, 2), nullable=True, server_default='0'),
            sa.Column('service_fee_pct', sa.Numeric(5, 2), nullable=True, server_default='10.0'),
            sa.Column('total_units', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('public_id', name='uq_room_type_public_id'),
            sa.Index('idx_roomtype_property', 'property_id'),
            sa.Index('idx_roomtype_active', 'is_active'),
        )

    # Create accommodation_inventory_blocks table
    if 'accommodation_inventory_blocks' not in existing_tables:
        op.create_table(
            'accommodation_inventory_blocks',
            sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column('public_id', sa.String(64), nullable=False),
            sa.Column('room_type_id', sa.BigInteger(), sa.ForeignKey('accommodation_room_types.id', ondelete='CASCADE'), nullable=False),
            sa.Column('date_range_start', sa.Date(), nullable=False),
            sa.Column('date_range_end', sa.Date(), nullable=False),
            sa.Column('units_blocked', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('reason', sa.String(30), nullable=False),
            sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('public_id', name='uq_inventory_block_public_id'),
            sa.Index('idx_inv_block_range', 'room_type_id', 'date_range_start', 'date_range_end'),
        )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'accommodation_inventory_blocks' in existing_tables:
        op.drop_table('accommodation_inventory_blocks')
    if 'accommodation_room_types' in existing_tables:
        op.drop_table('accommodation_room_types')