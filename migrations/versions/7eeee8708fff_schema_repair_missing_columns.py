"""schema_repair_missing_columns

Revision ID: 7eeee8708fff
Revises: d0bc88cfec8b
Create Date: 2026-04-08 13:48:50.071459

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '7eeee8708fff'
down_revision = 'd0bc88cfec8b'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    # =========================
    # FIX user_roles TABLE (SAFE)
    # =========================
    if not column_exists('user_roles', 'created_at'):
        op.add_column('user_roles', sa.Column('created_at', sa.DateTime(), nullable=True))

    if not column_exists('user_roles', 'updated_at'):
        op.add_column('user_roles', sa.Column('updated_at', sa.DateTime(), nullable=True))

    if not column_exists('user_roles', 'is_deleted'):
        op.add_column('user_roles', sa.Column('is_deleted', sa.Boolean(), nullable=True, server_default='false'))

    if not column_exists('user_roles', 'deleted_at'):
        op.add_column('user_roles', sa.Column('deleted_at', sa.DateTime(), nullable=True))

    # Only update existing columns safely
    op.execute("""
        UPDATE user_roles
        SET
            created_at = COALESCE(created_at, NOW()),
            updated_at = COALESCE(updated_at, NOW()),
            is_deleted = COALESCE(is_deleted, false)
    """)

    # =========================
    # FIX owner_audit_logs (SAFE)
    # =========================
    if not column_exists('owner_audit_logs', 'updated_at'):
        op.add_column('owner_audit_logs', sa.Column('updated_at', sa.DateTime(), nullable=True))

    op.execute("""
        UPDATE owner_audit_logs
        SET updated_at = COALESCE(updated_at, created_at)
    """)


def downgrade():
    op.drop_column('owner_audit_logs', 'updated_at')

    op.drop_column('user_roles', 'deleted_at')
    op.drop_column('user_roles', 'is_deleted')
    op.drop_column('user_roles', 'updated_at')
    op.drop_column('user_roles', 'created_at')
