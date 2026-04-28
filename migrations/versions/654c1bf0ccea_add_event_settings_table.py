"""add event_settings table

Revision ID: 654c1bf0ccea
Revises: ee770bb1ee78
Create Date: 2026-04-26 16:00:03.464143

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '654c1bf0ccea'
down_revision = 'ee770bb1ee78'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'event_settings',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('auto_publish', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('require_approval', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('event_manager_auto_approve', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('allow_free_events', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('max_capacity_limit', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('registration_open_days_before', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('auto_complete_events', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('auto_archive_after_days', sa.Integer(), nullable=False, server_default='90'),
        sa.Column('allow_organiser_cancel', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('allow_organiser_delete', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notify_admin_on_submit', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notify_organiser_on_decision', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notify_organiser_on_suspend', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('allow_multiple_ticket_types', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('max_ticket_types_per_event', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('allow_discount_codes', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('show_attendee_count', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('show_remaining_capacity', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('updated_by_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Insert the single default settings row immediately
    op.execute("""
        INSERT INTO event_settings (
            auto_publish, require_approval, event_manager_auto_approve,
            allow_free_events, max_capacity_limit, registration_open_days_before,
            auto_complete_events, auto_archive_after_days,
            allow_organiser_cancel, allow_organiser_delete,
            notify_admin_on_submit, notify_organiser_on_decision,
            notify_organiser_on_suspend, allow_multiple_ticket_types,
            max_ticket_types_per_event, allow_discount_codes,
            show_attendee_count, show_remaining_capacity,
            is_deleted, created_at, updated_at
        ) VALUES (
            false, true, true,
            true, 0, 0,
            true, 90,
            true, true,
            true, true,
            true, true,
            10, true,
            true, false,
            false, NOW(), NOW()
        )
    """)


def downgrade():
    op.drop_table('event_settings')