"""add_driver_profile_onboarding

Revision ID: e9c505703ce2
Revises: add_auth_configuration
Create Date: 2026-05-04 18:15:54.718779
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e9c505703ce2'
down_revision = 'add_auth_configuration'
branch_labels = None
depends_on = None


def upgrade():
    # -------------------------------
    # 1. ACCOUNTS FK CHANGE
    # -------------------------------
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.drop_constraint('accounts_user_id_fkey', type_='foreignkey')

    # -------------------------------
    # 2. AUTH CONFIGURATIONS (SAFE ADD)
    # -------------------------------

    # Step 1: Add columns as NULLABLE
    with op.batch_alter_table('auth_configurations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_deleted', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))

    # Step 2: Backfill existing rows
    op.execute("""
        UPDATE auth_configurations
        SET is_deleted = FALSE
        WHERE is_deleted IS NULL
    """)

    # Step 3: Enforce NOT NULL + DEFAULT + INDEXES
    with op.batch_alter_table('auth_configurations', schema=None) as batch_op:
        batch_op.alter_column(
            'is_deleted',
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.false()
        )

        batch_op.create_index(
            'ix_auth_configurations_created_at',
            ['created_at'],
            unique=False
        )

        batch_op.create_index(
            'ix_auth_configurations_is_deleted',
            ['is_deleted'],
            unique=False
        )

    # -------------------------------
    # 3. TRANSACTIONS FK FIX
    # -------------------------------
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_transactions_account_id', type_='foreignkey')

        batch_op.create_foreign_key(
            'fk_transactions_account_id',
            'accounts',
            ['account_id'],
            ['id']
        )


def downgrade():
    # -------------------------------
    # 1. TRANSACTIONS FK ROLLBACK
    # -------------------------------
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_transactions_account_id', type_='foreignkey')

        batch_op.create_foreign_key(
            'fk_transactions_account_id',
            'accounts',
            ['account_id'],
            ['id'],
            ondelete='SET NULL'
        )

    # -------------------------------
    # 2. AUTH CONFIGURATIONS ROLLBACK
    # -------------------------------
    with op.batch_alter_table('auth_configurations', schema=None) as batch_op:
        batch_op.drop_index('ix_auth_configurations_is_deleted')
        batch_op.drop_index('ix_auth_configurations_created_at')
        batch_op.drop_column('deleted_at')
        batch_op.drop_column('is_deleted')

    # -------------------------------
    # 3. ACCOUNTS FK ROLLBACK
    # -------------------------------
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'accounts_user_id_fkey',
            'users',
            ['user_id'],
            ['id'],
            ondelete='CASCADE'
        )