"""force_sync_audit_columns

Revision ID: 227e9e065f95
Revises: 425c8da214bc
Create Date: 2026-04-10 02:36:33.974894

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '227e9e065f95'
down_revision = '425c8da214bc'
branch_labels = None
depends_on = None


def upgrade():
    # Force add is_deleted and deleted_at to all tables if they don't exist
    op.execute("""
    DO $$
    DECLARE
        t record;
    BEGIN
        FOR t IN
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            AND tablename NOT IN ('alembic_version')
        LOOP
            -- Add is_deleted
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = t.tablename AND column_name = 'is_deleted') THEN
                EXECUTE format('ALTER TABLE %I ADD COLUMN is_deleted BOOLEAN DEFAULT false NOT NULL', t.tablename);
                EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_is_deleted ON %I (is_deleted)', t.tablename, t.tablename);
            END IF;

            -- Add deleted_at
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = t.tablename AND column_name = 'deleted_at') THEN
                EXECUTE format('ALTER TABLE %I ADD COLUMN deleted_at TIMESTAMP WITHOUT TIME ZONE NULL', t.tablename);
                EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_deleted_at ON %I (deleted_at)', t.tablename, t.tablename);
            END IF;
        END LOOP;
    END $$;
    """)

def downgrade():
    # Downgrade logic is optional here since we are forcing a sync,
    # but normally you would drop the columns added above.
    pass
