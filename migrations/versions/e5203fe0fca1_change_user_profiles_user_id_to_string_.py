"""Change user_profiles.user_id to String(64) and enforce uniqueness on users.user_id

Revision ID: e5203fe0fca1
Revises: e5d35d2d2742
Create Date: 2026-02-02 23:24:07.378107
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = 'e5203fe0fca1'
down_revision = 'e5d35d2d2742'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # 1) Ensure users.user_id is unique and indexed
    conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_users_user_id
        ON users (user_id)
    """))

    # 2) Drop old FK (user_profiles.user_id -> users.id)
    try:
        op.drop_constraint('user_profiles_user_id_fkey', 'user_profiles', type_='foreignkey')
    except Exception:
        pass

    # 3) Alter user_profiles.user_id from BIGINT to String(64)
    with op.batch_alter_table('user_profiles') as batch_op:
        batch_op.alter_column(
            'user_id',
            existing_type=sa.BigInteger(),
            type_=sa.String(length=64),
            nullable=False
        )

    # 4) Backfill user_profiles.user_id with UUIDs from users.user_id
    conn.execute(text("""
        UPDATE user_profiles
        SET user_id = u.user_id
        FROM users u
        WHERE user_profiles.user_id::text = u.id::text
    """))

    # 5) Create new FK (user_profiles.user_id -> users.user_id)
    op.create_foreign_key(
        'user_profiles_user_id_fkey',
        'user_profiles', 'users',
        ['user_id'], ['user_id'],
        ondelete='CASCADE'
    )

    # 6) Create index on user_profiles.user_id if not exists
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_user_profiles_user_id
        ON user_profiles (user_id)
    """))


def downgrade():
    conn = op.get_bind()

    # 1) Drop FK to users.user_id
    try:
        op.drop_constraint('user_profiles_user_id_fkey', 'user_profiles', type_='foreignkey')
    except Exception:
        pass

    # 2) Drop index on user_profiles.user_id
    conn.execute(text("DROP INDEX IF EXISTS ix_user_profiles_user_id"))

    # 3) Convert user_profiles.user_id back to BIGINT
    with op.batch_alter_table('user_profiles') as batch_op:
        batch_op.alter_column(
            'user_id',
            existing_type=sa.String(length=64),
            type_=sa.BigInteger(),
            nullable=False
        )

    # 4) Recreate FK to users.id
    op.create_foreign_key(
        'user_profiles_user_id_fkey',
        'user_profiles', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )

    # 5) Drop unique index on users.user_id (if desired)
    conn.execute(text("DROP INDEX IF EXISTS ux_users_user_id"))
