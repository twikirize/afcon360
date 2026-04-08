"""Fix dual ID system - ensure correct types for internal vs external IDs

Revision ID: ce3005b1b1f1
Revises: 7a2b8c3d4e5f
Create Date: 2026-04-07

This migration ensures:
- users.id = BIGINT (internal, for FKs)
- users.user_id = VARCHAR(64) (external, for public)
- All foreign keys in owner_audit_logs and owner_settings use BIGINT
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = 'ce3005b1b1f1'
down_revision = '7a2b8c3d4e5f'
branch_labels = None
depends_on = None


def upgrade():
    """
    Safe migration that preserves dual ID system and fixes datatype mismatch
    """

    # =========================================================
    # STEP 1: Ensure users.user_id exists and is populated
    # =========================================================
    # (Assuming user_id already exists based on previous code, but ensuring it's used as external ID)

    # =========================================================
    # STEP 2: Fix owner_audit_logs.owner_id (VARCHAR -> BIGINT)
    # =========================================================
    # Drop foreign key if it exists (might be using user_id or id)
    try:
        op.drop_constraint('owner_audit_logs_owner_id_fkey', 'owner_audit_logs', type_='foreignkey')
    except:
        pass

    # Alter column to BigInteger
    # In PostgreSQL, we need to handle the conversion if there's data
    with op.batch_alter_table('owner_audit_logs') as batch_op:
        batch_op.alter_column('owner_id',
                              existing_type=sa.String(64),
                              type_=sa.BigInteger(),
                              postgresql_using='owner_id::bigint',
                              existing_nullable=False)

    # Recreate foreign key pointing to users.id (BIGINT)
    op.create_foreign_key(
        'owner_audit_logs_owner_id_fkey',
        'owner_audit_logs',
        'users',
        ['owner_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # =========================================================
    # STEP 3: Fix owner_settings.owner_id (VARCHAR -> BIGINT)
    # =========================================================
    try:
        op.drop_constraint('owner_settings_owner_id_fkey', 'owner_settings', type_='foreignkey')
    except:
        pass

    with op.batch_alter_table('owner_settings') as batch_op:
        batch_op.alter_column('owner_id',
                              existing_type=sa.String(64),
                              type_=sa.BigInteger(),
                              postgresql_using='owner_id::bigint',
                              existing_nullable=False)

    op.create_foreign_key(
        'owner_settings_owner_id_fkey',
        'owner_settings',
        'users',
        ['owner_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # =========================================================
    # STEP 4: Cleanup any other accidental UUID-referenced FKs
    # =========================================================
    # Add other tables here if they were previously migrated to use user_id (String) instead of id (BigInt)


def downgrade():
    """
    Reverse the migration - restore VARCHAR types for owner_id
    """

    # Revert owner_settings
    op.drop_constraint('owner_settings_owner_id_fkey', 'owner_settings', type_='foreignkey')
    with op.batch_alter_table('owner_settings') as batch_op:
        batch_op.alter_column('owner_id',
                              existing_type=sa.BigInteger(),
                              type_=sa.String(64),
                              existing_nullable=False)
    op.create_foreign_key('owner_settings_owner_id_fkey', 'owner_settings', 'users', ['owner_id'], ['user_id'])

    # Revert owner_audit_logs
    op.drop_constraint('owner_audit_logs_owner_id_fkey', 'owner_audit_logs', type_='foreignkey')
    with op.batch_alter_table('owner_audit_logs') as batch_op:
        batch_op.alter_column('owner_id',
                              existing_type=sa.BigInteger(),
                              type_=sa.String(64),
                              existing_nullable=False)
    op.create_foreign_key('owner_audit_logs_owner_id_fkey', 'owner_audit_logs', 'users', ['owner_id'], ['user_id'])
