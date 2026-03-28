"""Add context fields as strings

Revision ID: 5355197e7f6a
Revises: 171e85b93e68
Create Date: 2026-03-26 22:49:21.494925

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '5355197e7f6a'
down_revision = '171e85b93e68'
branch_labels = None
depends_on = None


def upgrade():
    # ==========================================
    # 1. Convert ENUM columns to VARCHAR (existing)
    # ==========================================
    with op.batch_alter_table('accommodation_booking_history', schema=None) as batch_op:
        batch_op.alter_column('from_status',
               existing_type=postgresql.ENUM('PENDING', 'CONFIRMED', 'CHECKED_IN', 'CHECKED_OUT', 'CANCELLED', 'REFUNDED', 'NO_SHOW', name='accommodationbookingstatus'),
               type_=sa.String(length=50),
               existing_nullable=True)
        batch_op.alter_column('to_status',
               existing_type=postgresql.ENUM('PENDING', 'CONFIRMED', 'CHECKED_IN', 'CHECKED_OUT', 'CANCELLED', 'REFUNDED', 'NO_SHOW', name='accommodationbookingstatus'),
               type_=sa.String(length=50),
               existing_nullable=False)

    # ==========================================
    # 2. Convert ENUM columns in bookings table
    # ==========================================
    with op.batch_alter_table('accommodation_bookings', schema=None) as batch_op:
        batch_op.alter_column('payment_method',
               existing_type=postgresql.ENUM('WALLET', 'CARD', 'MOBILE_MONEY', 'BANK_TRANSFER', name='accommodationpaymentmethod'),
               type_=sa.String(length=50),
               existing_nullable=True)
        batch_op.alter_column('payment_status',
               existing_type=postgresql.ENUM('PENDING', 'PAID', 'FAILED', 'REFUNDED', 'PARTIAL_REFUND', name='accommodationpaymentstatus'),
               type_=sa.String(length=50),
               nullable=False)
        batch_op.alter_column('status',
               existing_type=postgresql.ENUM('PENDING', 'CONFIRMED', 'CHECKED_IN', 'CHECKED_OUT', 'CANCELLED', 'REFUNDED', 'NO_SHOW', name='accommodationbookingstatus'),
               type_=sa.String(length=50),
               existing_nullable=False)

    # ==========================================
    # 3. ADD CONTEXT COLUMNS (SAFELY)
    # ==========================================
    # Step 3a: Add context_type as NULLABLE first
    with op.batch_alter_table('accommodation_bookings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('context_type', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('context_id', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('context_metadata', sa.JSON(), nullable=True))

    # Step 3b: Populate existing rows with default value
    op.execute("UPDATE accommodation_bookings SET context_type = 'none' WHERE context_type IS NULL")

    # Step 3c: Now make context_type NOT NULL
    with op.batch_alter_table('accommodation_bookings', schema=None) as batch_op:
        batch_op.alter_column('context_type', nullable=False)
        batch_op.create_index('idx_booking_context', ['context_type', 'context_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_accommodation_bookings_context_id'), ['context_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_accommodation_bookings_context_type'), ['context_type'], unique=False)


def downgrade():
    # ==========================================
    # Reverse order
    # ==========================================
    with op.batch_alter_table('accommodation_bookings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_accommodation_bookings_context_type'))
        batch_op.drop_index(batch_op.f('ix_accommodation_bookings_context_id'))
        batch_op.drop_index('idx_booking_context')
        batch_op.drop_column('context_metadata')
        batch_op.drop_column('context_id')
        batch_op.drop_column('context_type')

    with op.batch_alter_table('accommodation_bookings', schema=None) as batch_op:
        batch_op.alter_column('status',
               existing_type=sa.String(length=50),
               type_=postgresql.ENUM('PENDING', 'CONFIRMED', 'CHECKED_IN', 'CHECKED_OUT', 'CANCELLED', 'REFUNDED', 'NO_SHOW', name='accommodationbookingstatus'),
               existing_nullable=False)
        batch_op.alter_column('payment_status',
               existing_type=sa.String(length=50),
               type_=postgresql.ENUM('PENDING', 'PAID', 'FAILED', 'REFUNDED', 'PARTIAL_REFUND', name='accommodationpaymentstatus'),
               nullable=True)
        batch_op.alter_column('payment_method',
               existing_type=sa.String(length=50),
               type_=postgresql.ENUM('WALLET', 'CARD', 'MOBILE_MONEY', 'BANK_TRANSFER', name='accommodationpaymentmethod'),
               existing_nullable=True)

    with op.batch_alter_table('accommodation_booking_history', schema=None) as batch_op:
        batch_op.alter_column('to_status',
               existing_type=sa.String(length=50),
               type_=postgresql.ENUM('PENDING', 'CONFIRMED', 'CHECKED_IN', 'CHECKED_OUT', 'CANCELLED', 'REFUNDED', 'NO_SHOW', name='accommodationbookingstatus'),
               existing_nullable=False)
        batch_op.alter_column('from_status',
               existing_type=sa.String(length=50),
               type_=postgresql.ENUM('PENDING', 'CONFIRMED', 'CHECKED_IN', 'CHECKED_OUT', 'CANCELLED', 'REFUNDED', 'NO_SHOW', name='accommodationbookingstatus'),
               existing_nullable=True)

    # ### end Alembic commands ###
