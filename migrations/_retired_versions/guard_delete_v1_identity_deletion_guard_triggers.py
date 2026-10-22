"""add deletion guard triggers on user_roles and users

Revision ID: guard_delete_v1
Revises: 43a863fe3531
Create Date: 2026-09-15 16:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'guard_delete_v1'
down_revision = '43a863fe3531'
branch_labels = None
depends_on = None


def upgrade():
    # Trigger function: blocks DELETE on user_roles unless the transaction
    # has set the session GUC ``app.guard.authorized_deletion = 'true'``.
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION guard_user_roles_delete()
        RETURNS trigger AS $$
        BEGIN
          IF current_setting('app.guard.authorized_deletion', true) IS DISTINCT FROM 'true' THEN
            RAISE EXCEPTION
              'Unauthorized DELETE on user_roles: '
              'session GUC app.guard.authorized_deletion is not set to ''true''. '
              'Use app.auth.deletion_guard.authorize_deletion() in the sanctioned service path.'
              USING ERRCODE = '42501';
          END IF;
          RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;
    """))
    op.execute(sa.text("""
        DROP TRIGGER IF EXISTS trg_guard_user_roles_delete ON user_roles;
    """))
    op.execute(sa.text("""
        CREATE TRIGGER trg_guard_user_roles_delete
            BEFORE DELETE ON user_roles
            FOR EACH ROW
            EXECUTE FUNCTION guard_user_roles_delete();
    """))

    # Trigger function: blocks hard DELETE on users (soft-delete uses UPDATE
    # and is unaffected).
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION guard_users_delete()
        RETURNS trigger AS $$
        BEGIN
          IF current_setting('app.guard.authorized_deletion', true) IS DISTINCT FROM 'true' THEN
            RAISE EXCEPTION
              'Unauthorized DELETE on users: '
              'session GUC app.guard.authorized_deletion is not set to ''true''. '
              'Use app.auth.deletion_guard.authorize_deletion() in the sanctioned service path.'
              USING ERRCODE = '42501';
          END IF;
          RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;
    """))
    op.execute(sa.text("""
        DROP TRIGGER IF EXISTS trg_guard_users_delete ON users;
    """))
    op.execute(sa.text("""
        CREATE TRIGGER trg_guard_users_delete
            BEFORE DELETE ON users
            FOR EACH ROW
            EXECUTE FUNCTION guard_users_delete();
    """))


def downgrade():
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_guard_user_roles_delete ON user_roles;"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS guard_user_roles_delete();"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_guard_users_delete ON users;"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS guard_users_delete();"))
