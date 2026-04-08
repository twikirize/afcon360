"""final_dual_id_and_theme_system_updates

Revision ID: ab8d0f8c3ee8
Revises: 8e23ba21b140
Create Date: 2026-04-07 23:26:52.034651
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ab8d0f8c3ee8'
down_revision = '8e23ba21b140'
branch_labels = None
depends_on = None


def upgrade():
    # ==============================
    # MASTER ARCHITECTURAL PATCH
    # ==============================

    # 1. TIMESTAMPS (Detect and add missing created_at/updated_at with defaults)
    tables_to_patch = [
        'api_audit_logs', 'data_access_logs', 'data_change_logs', 'financial_audit_logs',
        'idempotency_keys', 'security_event_logs', 'agent_commissions', 'audit_logs',
        'compliance_audit_logs', 'compliance_settings', 'individual_documents',
        'individual_verifications', 'organisation_audit_logs', 'organisation_controllers',
        'organisation_documents', 'organisation_kyb_checks', 'organisation_kyb_documents',
        'organisation_licenses', 'organisation_ubos', 'organisation_verifications',
        'payout_requests', 'role_permissions', 'owner_audit_logs', 'accommodation_availability_rules',
        'accommodation_photos', 'accommodation_amenities_master', 'accommodation_property_amenities',
        'accommodation_rules', 'event_ticket_types', 'org_member_permissions',
        'org_role_permissions', 'org_user_roles', 'organisation_drivers',
        'user_profile_audit', 'wallet_transactions', 'accommodation_blocked_dates',
        'accommodation_booking_history', 'ledger_entries', 'api_keys', 'mfa_secrets', 'sessions', 'user_roles'
    ]

    for table in tables_to_patch:
        # Check columns dynamically within the migration
        conn = op.get_bind()
        inspector = sa.inspect(conn)
        columns = [col['name'] for col in inspector.get_columns(table)]

        if 'created_at' not in columns:
            op.add_column(table, sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
            op.create_index(f'ix_{table}_created_at', table, ['created_at'], unique=False)

        if 'updated_at' not in columns:
            op.add_column(table, sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
            op.create_index(f'ix_{table}_updated_at', table, ['updated_at'], unique=False)

    # 2. BIGINT UPGRADES (INTEGER -> BIGINT for IDs and FKs)
    # Fan Profiles, KYC Records, and Content/Theme tables
    tables_to_bigint = [
        ('fan_profiles', ['id']),
        ('kyc_records', ['id']),
        ('manageable_categories', ['id']),
        ('manageable_items', ['id', 'category_id']),
        ('content_submissions', ['id', 'item_id', 'category_id']),
        ('user_dashboard_configs', ['id']),
        ('global_themes', ['id']),
        ('event_themes', ['event_id'])
    ]

    for table, columns in tables_to_bigint:
        for col in columns:
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.alter_column(col,
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    postgresql_using=f'{col}::bigint',
                    existing_nullable=False if col in ['id', 'event_id'] else True
                )

    # 3. MISSING FK INDEXES (Performance)
    fks_to_index = [
        ('accommodation_properties', 'verified_by'),
        ('agent_commissions', ['paid_by', 'recipient_id']),
        ('compliance_audit_logs', 'decided_by'),
        ('compliance_settings', 'updated_by'),
        ('driver_profiles', ['created_by', 'license_verified_by', 'updated_by']),
        ('events', ['approved_by_id', 'organizer_id']),
        ('individual_documents', 'user_id'),
        ('individual_verifications', 'reviewer_id'),
        ('organisation_audit_logs', 'changed_by'),
        ('organisation_controllers', ['added_by', 'organisation_id', 'user_id']),
        ('organisation_documents', 'uploaded_by'),
        ('organisation_kyb_checks', 'organisation_id'),
        ('organisation_kyb_documents', 'organisation_id'),
        ('organisation_transport_profiles', ['created_by', 'updated_by']),
        ('organisation_ubos', ['organisation_id', 'user_id', 'verified_by']),
        ('organisation_verifications', ['organisation_id', 'reviewer_id']),
        ('payout_requests', ['approved_by', 'paid_by']),
        ('transport_settings', 'last_modified_by'),
        ('accommodation_bookings', 'cancelled_by_user_id'),
        ('driver_vehicle_history', ['authorized_by', 'replacement_vehicle_id']),
        ('event_roles', 'assigned_by_id'),
        ('event_ticket_types', 'event_id'),
        ('org_member_permissions', 'granted_by'),
        ('transport_scheduled_routes', ['current_driver_id', 'current_vehicle_id']),
        ('accommodation_blocked_dates', 'created_by'),
        ('accommodation_booking_history', 'changed_by_user_id'),
        ('accommodation_reviews', 'moderated_by'),
        ('event_registrations', ['checked_in_by_id', 'ticket_type_id']),
        ('ledger_entries', 'counterparty_wallet_id'),
        ('transport_bookings', ['assigned_driver_id', 'assigned_route_id', 'assigned_vehicle_id']),
        ('transport_incidents', ['assigned_to', 'driver_id', 'user_id', 'vehicle_id']),
        ('content_submissions', ['category_id', 'item_id', 'reviewed_by', 'submitted_by', 'submitted_by_org']),
        ('manageable_items', ['created_by', 'owned_by_org']),
        ('user_theme_preferences', 'user_id'),
        ('event_themes', 'event_id')
    ]

    for table, cols in fks_to_index:
        if isinstance(cols, str): cols = [cols]
        for col in cols:
            # Generate index name safely
            idx_name = f'ix_{table}_{col}'
            # Check if index exists
            conn = op.get_bind()
            inspector = sa.inspect(conn)
            indexes = [idx['name'] for idx in inspector.get_indexes(table)]
            if idx_name not in indexes:
                op.create_index(idx_name, table, [col], unique=False)


def downgrade():
    # Downsizing BIGINT back to INTEGER is generally unsafe and omitted for architectural stability.
    # Removal of indexes and timestamps is also omitted to prevent accidental data loss or performance regression.
    pass
