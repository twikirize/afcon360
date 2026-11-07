"""Add OCI_EMAIL to NotificationChannel enum

Revision ID: 20261106180825
Revises: h3b20261104
Create Date: 2026-11-06 18:08:25.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20261106180825'
down_revision = 'h3b20261104'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Update the CHECK constraint on notifications.channel to include 'oci_email'
    # The constraint name is ck_notifications_channel
    op.execute("""
        ALTER TABLE notifications
        DROP CONSTRAINT IF EXISTS ck_notifications_channel
    """)
    op.execute("""
        ALTER TABLE notifications
        ADD CONSTRAINT ck_notifications_channel
        CHECK (channel IN (
            'in_app', 'email', 'oci_email', 'sms', 'push', 'webhook'
        ))
    """)


def downgrade() -> None:
    # Revert to the original enum values
    op.execute("""
        ALTER TABLE notifications
        DROP CONSTRAINT IF EXISTS ck_notifications_channel
    """)
    op.execute("""
        ALTER TABLE notifications
        ADD CONSTRAINT ck_notifications_channel
        CHECK (channel IN (
            'in_app', 'email', 'sms', 'push', 'webhook'
        ))
    """)