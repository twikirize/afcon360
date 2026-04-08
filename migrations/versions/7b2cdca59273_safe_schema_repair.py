"""safe_schema_repair

Revision ID: 7b2cdca59273
Revises: 7eeee8708fff
Create Date: 2026-04-08

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '7b2cdca59273'
down_revision = '7eeee8708fff'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def safe_add_column(table, column):
    if not column_exists(table, column.name):
        op.add_column(table, column)


def upgrade():
    # =========================
    # USER_ROLES FIXES
    # =========================
    safe_add_column('user_roles', sa.Column('is_deleted', sa.Boolean(), nullable=True, server_default='false'))
    safe_add_column('user_roles', sa.Column('deleted_at', sa.DateTime(), nullable=True))
    safe_add_column('user_roles', sa.Column('created_at', sa.DateTime(), nullable=True))
    safe_add_column('user_roles', sa.Column('updated_at', sa.DateTime(), nullable=True))

    # =========================
    # OWNER AUDIT LOGS FIXES
    # =========================
    safe_add_column('owner_audit_logs', sa.Column('updated_at', sa.DateTime(), nullable=True))

    # =========================
    # OPTIONAL HARDENING
    # =========================
    # Ensure defaults for soft delete
    op.execute("""
        UPDATE user_roles
        SET is_deleted = COALESCE(is_deleted, false)
    """)


def downgrade():
    pass
