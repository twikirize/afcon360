"""add_missing_columns_to_system_configs

Revision ID: 273c374bade0
Revises: 330ce9bd4864
Create Date: 2026-07-23 14:29:55.644439

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '273c374bade0'
down_revision = '330ce9bd4864'
branch_labels = None
depends_on = None


def upgrade():
    # ============================================================
    # STEP 1: ✅ ADD MISSING COLUMNS TO system_configs FIRST
    # ============================================================
    with op.batch_alter_table('system_configs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('value_type', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('category', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('is_public', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('requires_restart', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('updated_by', sa.BigInteger(), nullable=True))
        batch_op.alter_column('value',
               existing_type=sa.TEXT(),
               nullable=True)
        batch_op.alter_column('updated_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True,
               existing_server_default=sa.text('CURRENT_TIMESTAMP'))
        batch_op.drop_index(batch_op.f('ix_system_configs_updated_at'))
        batch_op.drop_constraint(batch_op.f('uq_system_configs_key'), type_='unique')
        batch_op.drop_index(batch_op.f('ix_system_configs_key'))
        batch_op.create_index(batch_op.f('ix_system_configs_key'), ['key'], unique=True)
        batch_op.create_index(batch_op.f('ix_system_configs_category'), ['category'], unique=False)
        batch_op.drop_constraint(batch_op.f('system_configs_created_by_fkey'), type_='foreignkey')
        batch_op.create_foreign_key(None, 'users', ['updated_by'], ['id'])
        batch_op.drop_column('created_by')

    # ============================================================
    # STEP 2: ✅ COPY DATA FROM system_settings TO system_configs
    # ============================================================
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'system_settings' in tables:
        # Check if there's data - FIXED: use sa.text()
        result = conn.execute(sa.text("SELECT COUNT(*) FROM system_settings"))
        count = result.fetchone()[0]

        if count > 0:
            # Copy data from system_settings to system_configs - FIXED: use sa.text()
            conn.execute(sa.text("""
                INSERT INTO system_configs (
                    key, value, value_type, category, description, 
                    is_public, requires_restart, updated_by, updated_at, 
                    created_at, is_deleted
                )
                SELECT 
                    key, value, value_type, category, description, 
                    is_public, requires_restart, updated_by, updated_at, 
                    COALESCE(created_at, NOW()), 
                    COALESCE(is_deleted, FALSE)
                FROM system_settings
                ON CONFLICT (key) DO UPDATE SET 
                    value = EXCLUDED.value,
                    value_type = EXCLUDED.value_type,
                    category = EXCLUDED.category,
                    description = EXCLUDED.description,
                    is_public = EXCLUDED.is_public,
                    requires_restart = EXCLUDED.requires_restart,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = EXCLUDED.updated_at
            """))
            print(f"✅ Copied {count} records from system_settings to system_configs")
        else:
            print("⚠️ system_settings exists but has 0 rows - skipping copy")
    else:
        print("ℹ️ system_settings table does not exist - skipping copy")

    # ============================================================
    # STEP 3: ✅ DROP system_settings (SAFE - data is copied)
    # ============================================================
    with op.batch_alter_table('system_settings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_system_settings_category'))
        batch_op.drop_index(batch_op.f('ix_system_settings_created_at'))
        batch_op.drop_index(batch_op.f('ix_system_settings_is_deleted'))
        batch_op.drop_index(batch_op.f('ix_system_settings_key'))

    op.drop_table('system_settings')
    print("✅ Dropped system_settings table (data migrated to system_configs)")

    # ============================================================
    # STEP 4: ✅ UPDATE content_flags
    # ============================================================
    with op.batch_alter_table('content_flags', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_content_flags_risk_score'))
        batch_op.create_index('ix_content_flags_risk_score', ['risk_score', 'status'], unique=False)


def downgrade():
    # ============================================================
    # STEP 1: ✅ RESTORE content_flags
    # ============================================================
    with op.batch_alter_table('content_flags', schema=None) as batch_op:
        batch_op.drop_index('ix_content_flags_risk_score')
        batch_op.create_index(batch_op.f('ix_content_flags_risk_score'), ['risk_score'], unique=False)

    # ============================================================
    # STEP 2: ✅ REVERT system_configs (remove columns)
    # ============================================================
    with op.batch_alter_table('system_configs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_by', sa.BIGINT(), autoincrement=False, nullable=True))
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key(batch_op.f('system_configs_created_by_fkey'), 'users', ['created_by'], ['id'])
        batch_op.drop_index(batch_op.f('ix_system_configs_category'))
        batch_op.drop_index(batch_op.f('ix_system_configs_key'))
        batch_op.create_index(batch_op.f('ix_system_configs_key'), ['key'], unique=False)
        batch_op.create_unique_constraint(batch_op.f('uq_system_configs_key'), ['key'], postgresql_nulls_not_distinct=False)
        batch_op.create_index(batch_op.f('ix_system_configs_updated_at'), ['updated_at'], unique=False)
        batch_op.alter_column('updated_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=False,
               existing_server_default=sa.text('CURRENT_TIMESTAMP'))
        batch_op.alter_column('value',
               existing_type=sa.TEXT(),
               nullable=False)
        batch_op.drop_column('updated_by')
        batch_op.drop_column('requires_restart')
        batch_op.drop_column('is_public')
        batch_op.drop_column('category')
        batch_op.drop_column('value_type')

    # ============================================================
    # STEP 3: ✅ RESTORE system_settings (simplified)
    # ============================================================
    op.create_table('system_settings',
        sa.Column('id', sa.BIGINT(), autoincrement=True, nullable=False),
        sa.Column('key', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
        sa.Column('value', sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column('value_type', sa.VARCHAR(length=20), autoincrement=False, nullable=True),
        sa.Column('category', sa.VARCHAR(length=50), autoincrement=False, nullable=True),
        sa.Column('description', sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column('is_public', sa.BOOLEAN(), autoincrement=False, nullable=True),
        sa.Column('requires_restart', sa.BOOLEAN(), autoincrement=False, nullable=True),
        sa.Column('updated_by', sa.BIGINT(), autoincrement=False, nullable=True),
        sa.Column('updated_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column('is_deleted', sa.BOOLEAN(), autoincrement=False, nullable=False),
        sa.Column('deleted_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('system_settings_pkey'))
    )
    with op.batch_alter_table('system_settings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_system_settings_key'), ['key'], unique=True)
        batch_op.create_index(batch_op.f('ix_system_settings_is_deleted'), ['is_deleted'], unique=False)
        batch_op.create_index(batch_op.f('ix_system_settings_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_system_settings_category'), ['category'], unique=False)

  # ### end Alembic commands ###