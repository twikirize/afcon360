"""Phase 6: Event ownership, transfers, permissions, organization roles

Revision ID: 80c9b2f7cb42
Revises: 6c994e0e5f9d
Create Date: 2026-04-16 18:48:24.502306

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '80c9b2f7cb42'
down_revision = '6c994e0e5f9d'
branch_labels = None
depends_on = None


def upgrade():
    # ============================================================
    # STEP 1: Create ENUM types safely (skip if already exists)
    # ============================================================
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'creatortype') THEN
                CREATE TYPE creatortype AS ENUM ('INDIVIDUAL', 'ORGANIZATION', 'SYSTEM');
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'ownertype') THEN
                CREATE TYPE ownertype AS ENUM ('INDIVIDUAL', 'ORGANIZATION', 'SYSTEM');
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'transferstatus') THEN
                CREATE TYPE transferstatus AS ENUM ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED');
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'discounttype') THEN
                CREATE TYPE discounttype AS ENUM ('PERCENTAGE', 'FIXED');
            END IF;
        END $$;
    """)

    # ============================================================
    # STEP 2: Enable UUID generation
    # ============================================================
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')

    # ============================================================
    # STEP 3: Create New Tables (postgresql.ENUM with create_type=False)
    # ============================================================
    op.create_table(
        'discount_codes',
        sa.Column('event_id', sa.BigInteger(), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column(
            'discount_type',
            postgresql.ENUM('PERCENTAGE', 'FIXED', name='discounttype', create_type=False),
            nullable=False,
        ),
        sa.Column('discount_value', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=True),
        sa.Column('valid_from', sa.DateTime(), nullable=False),
        sa.Column('valid_until', sa.DateTime(), nullable=True),
        sa.Column('usage_limit', sa.Integer(), nullable=True),
        sa.Column('used_count', sa.Integer(), nullable=False),
        sa.Column('minimum_order', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_discount_code'),
    )

    op.create_table(
        'event_transfer_logs',
        sa.Column('event_id', sa.BigInteger(), nullable=False),
        sa.Column(
            'from_owner_type',
            postgresql.ENUM('INDIVIDUAL', 'ORGANIZATION', 'SYSTEM', name='ownertype', create_type=False),
            nullable=False,
        ),
        sa.Column('from_owner_id', sa.BigInteger(), nullable=False),
        sa.Column(
            'to_owner_type',
            postgresql.ENUM('INDIVIDUAL', 'ORGANIZATION', 'SYSTEM', name='ownertype', create_type=False),
            nullable=False,
        ),
        sa.Column('to_owner_id', sa.BigInteger(), nullable=False),
        sa.Column('transferred_by_id', sa.BigInteger(), nullable=False),
        sa.Column('transferred_at', sa.DateTime(), nullable=True),
        sa.Column('extra_data', sa.JSON(), nullable=True),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['transferred_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'event_transfer_requests',
        sa.Column('event_id', sa.BigInteger(), nullable=False),
        sa.Column('from_user_id', sa.BigInteger(), nullable=True),
        sa.Column('from_organization_id', sa.BigInteger(), nullable=True),
        sa.Column('to_user_id', sa.BigInteger(), nullable=True),
        sa.Column('to_organization_id', sa.BigInteger(), nullable=True),
        sa.Column('requested_by_id', sa.BigInteger(), nullable=False),
        sa.Column(
            'status',
            postgresql.ENUM('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED', name='transferstatus', create_type=False),
            nullable=False,
        ),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('approved_by_id', sa.BigInteger(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['approved_by_id'], ['users.id']),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['from_organization_id'], ['organisations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['from_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['requested_by_id'], ['users.id']),
        sa.ForeignKeyConstraint(['to_organization_id'], ['organisations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['to_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ============================================================
    # STEP 4: Add columns to existing tables
    # ============================================================
    with op.batch_alter_table('event_registrations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('discount_code_applied', sa.String(length=50), nullable=True))
        batch_op.add_column(
            sa.Column('discount_amount', sa.Numeric(precision=10, scale=2), server_default='0', nullable=False)
        )

    with op.batch_alter_table('event_waitlist', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('notification_sent', sa.Boolean(), server_default='false', nullable=False)
        )
        batch_op.add_column(
            sa.Column('conversion_attempts', sa.Integer(), server_default='0', nullable=False)
        )

    # ============================================================
    # STEP 5: Add ownership columns to 'events'
    # ============================================================
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('public_id', sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column(
                'created_by_type',
                postgresql.ENUM('INDIVIDUAL', 'ORGANIZATION', 'SYSTEM', name='creatortype', create_type=False),
                server_default='INDIVIDUAL',
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column('organization_id', sa.BigInteger(), nullable=True))
        batch_op.add_column(
            sa.Column('is_system_event', sa.Boolean(), server_default='false', nullable=False)
        )
        batch_op.add_column(sa.Column('original_creator_id', sa.BigInteger(), nullable=True))
        batch_op.add_column(
            sa.Column(
                'current_owner_type',
                postgresql.ENUM('INDIVIDUAL', 'ORGANIZATION', 'SYSTEM', name='ownertype', create_type=False),
                server_default='INDIVIDUAL',
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column('current_owner_id', sa.BigInteger(), nullable=True))

    # ============================================================
    # STEP 6: Backfill and Finalize
    # ============================================================
    op.execute("UPDATE events SET public_id = gen_random_uuid()::text WHERE public_id IS NULL")
    op.execute("UPDATE events SET current_owner_id = organizer_id WHERE current_owner_id IS NULL")
    op.execute("UPDATE events SET original_creator_id = organizer_id WHERE original_creator_id IS NULL")

    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.alter_column('public_id', nullable=False)
        batch_op.alter_column('current_owner_id', nullable=False)
        batch_op.create_foreign_key(None, 'organisations', ['organization_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(None, 'users', ['original_creator_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')  # original_creator_id → users
        batch_op.drop_constraint(None, type_='foreignkey')  # organization_id → organisations
        batch_op.drop_column('current_owner_id')
        batch_op.drop_column('current_owner_type')
        batch_op.drop_column('original_creator_id')
        batch_op.drop_column('is_system_event')
        batch_op.drop_column('organization_id')
        batch_op.drop_column('created_by_type')
        batch_op.drop_column('public_id')

    with op.batch_alter_table('event_waitlist', schema=None) as batch_op:
        batch_op.drop_column('conversion_attempts')
        batch_op.drop_column('notification_sent')

    with op.batch_alter_table('event_registrations', schema=None) as batch_op:
        batch_op.drop_column('discount_amount')
        batch_op.drop_column('discount_code_applied')

    op.drop_table('event_transfer_requests')
    op.drop_table('event_transfer_logs')
    op.drop_table('discount_codes')

    op.execute("DROP TYPE IF EXISTS creatortype")
    op.execute("DROP TYPE IF EXISTS ownertype")
    op.execute("DROP TYPE IF EXISTS transferstatus")
    op.execute("DROP TYPE IF EXISTS discounttype")
