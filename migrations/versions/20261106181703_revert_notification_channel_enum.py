"""Revert NotificationChannel enum to original values (remove OCI_EMAIL)

Revision ID: 20261106181703
Revises: 20261106180825
Create Date: 2026-11-06 18:17:03.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20261106181703'
down_revision = '20261106180825'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # First, update existing rows with 'oci_email' to 'email'
    op.execute("""
        UPDATE notifications
        SET channel = 'email'
        WHERE channel = 'oci_email'
    """)
    # Then update the CHECK constraint
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


def downgrade() -> None:
    # Add back oci_email if needed
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