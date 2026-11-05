"""TZ-UNIFY-02b: convert remaining 54 naive created_at/updated_at columns

Revision ID: 31287acd4eb8
Revises: c8c6a2c5a3f9
Create Date: 2026-10-28 17:40 (recovered from compiled artifact .pyc)

Source restored during the owner-authorized TZ-UNIFY-02/03 migration-history
repair; op sequence re-recorded verbatim from the recovered compiled artifact
and verified against its bytecode operation counts.

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '31287acd4eb8'
down_revision = 'c8c6a2c5a3f9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('api_keys', schema=None) as batch_op:
        batch_op.alter_column('revoked_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    with op.batch_alter_table('auth_configurations', schema=None) as batch_op:
        batch_op.alter_column('updated_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=False)
    with op.batch_alter_table('backup_records', schema=None) as batch_op:
        batch_op.alter_column('started_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('completed_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    with op.batch_alter_table('compliance_case_notes', schema=None) as batch_op:
        batch_op.alter_column('created_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=False)
        batch_op.alter_column('updated_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=False)
        batch_op.alter_column('deleted_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    with op.batch_alter_table('compliance_cases', schema=None) as batch_op:
        batch_op.alter_column('assigned_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('escalated_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('sla_due_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('resolved_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('created_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=False)
        batch_op.alter_column('updated_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=False)
    with op.batch_alter_table('compliance_reports', schema=None) as batch_op:
        batch_op.alter_column('date_range_start', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('date_range_end', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('reviewed_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('approved_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('distributed_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('created_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=False)
        batch_op.alter_column('updated_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=False)
    with op.batch_alter_table('compliance_settings', schema=None) as batch_op:
        batch_op.alter_column('created_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=False)
        batch_op.alter_column('updated_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=False)
    with op.batch_alter_table('data_subject_requests', schema=None) as batch_op:
        batch_op.alter_column('verified_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('assigned_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('completed_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('sla_due_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('created_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=False)
        batch_op.alter_column('updated_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=False)
    with op.batch_alter_table('fan_profiles', schema=None) as batch_op:
        batch_op.alter_column('activated_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('deactivated_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    with op.batch_alter_table('kyc_records', schema=None) as batch_op:
        batch_op.alter_column('verified_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('compliance_reviewed_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('referred_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('expiry_date', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    with op.batch_alter_table('mfa_secrets', schema=None) as batch_op:
        batch_op.alter_column('last_used', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('created_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=False)
    with op.batch_alter_table('rate_limit_breaches', schema=None) as batch_op:
        batch_op.alter_column('notified_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    with op.batch_alter_table('server_sessions', schema=None) as batch_op:
        batch_op.alter_column('expires_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=False)
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.alter_column('expires_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=False)
        batch_op.alter_column('revoked_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    with op.batch_alter_table('system_configs', schema=None) as batch_op:
        batch_op.alter_column('updated_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), nullable=False)
    with op.batch_alter_table('user_dashboard_contexts', schema=None) as batch_op:
        batch_op.alter_column('last_updated', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
    with op.batch_alter_table('user_roles', schema=None) as batch_op:
        batch_op.alter_column('assigned_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=False)
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('password_changed_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('password_expires_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('email_verified_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('phone_verified_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('activated_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('deleted_at', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('locked_until', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('last_login', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('transaction_pin_locked_until', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('emergency_access_granted', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)
        batch_op.alter_column('emergency_access_expires', existing_type=sa.DateTime(), type_=sa.DateTime(timezone=True), existing_nullable=True)


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('emergency_access_expires', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('emergency_access_granted', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('transaction_pin_locked_until', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('last_login', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('locked_until', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('deleted_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('activated_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('phone_verified_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('email_verified_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('password_expires_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('password_changed_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    with op.batch_alter_table('user_roles', schema=None) as batch_op:
        batch_op.alter_column('assigned_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=False)
    with op.batch_alter_table('user_dashboard_contexts', schema=None) as batch_op:
        batch_op.alter_column('last_updated', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    with op.batch_alter_table('system_configs', schema=None) as batch_op:
        batch_op.alter_column('updated_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), nullable=True)
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.alter_column('revoked_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('expires_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=False)
    with op.batch_alter_table('server_sessions', schema=None) as batch_op:
        batch_op.alter_column('expires_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=False)
    with op.batch_alter_table('rate_limit_breaches', schema=None) as batch_op:
        batch_op.alter_column('notified_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    with op.batch_alter_table('mfa_secrets', schema=None) as batch_op:
        batch_op.alter_column('created_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=False)
        batch_op.alter_column('last_used', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    with op.batch_alter_table('kyc_records', schema=None) as batch_op:
        batch_op.alter_column('expiry_date', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('referred_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('compliance_reviewed_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('verified_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    with op.batch_alter_table('fan_profiles', schema=None) as batch_op:
        batch_op.alter_column('deactivated_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('activated_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    with op.batch_alter_table('data_subject_requests', schema=None) as batch_op:
        batch_op.alter_column('updated_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=False)
        batch_op.alter_column('created_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=False)
        batch_op.alter_column('sla_due_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('completed_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('assigned_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('verified_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    with op.batch_alter_table('compliance_settings', schema=None) as batch_op:
        batch_op.alter_column('updated_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=False)
        batch_op.alter_column('created_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=False)
    with op.batch_alter_table('compliance_reports', schema=None) as batch_op:
        batch_op.alter_column('updated_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=False)
        batch_op.alter_column('created_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=False)
        batch_op.alter_column('distributed_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('approved_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('reviewed_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('date_range_end', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('date_range_start', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    with op.batch_alter_table('compliance_cases', schema=None) as batch_op:
        batch_op.alter_column('updated_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=False)
        batch_op.alter_column('created_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=False)
        batch_op.alter_column('resolved_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('sla_due_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('escalated_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('assigned_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    with op.batch_alter_table('compliance_case_notes', schema=None) as batch_op:
        batch_op.alter_column('deleted_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('updated_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=False)
        batch_op.alter_column('created_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=False)
    with op.batch_alter_table('backup_records', schema=None) as batch_op:
        batch_op.alter_column('completed_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
        batch_op.alter_column('started_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
    with op.batch_alter_table('auth_configurations', schema=None) as batch_op:
        batch_op.alter_column('updated_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=False)
    with op.batch_alter_table('api_keys', schema=None) as batch_op:
        batch_op.alter_column('revoked_at', existing_type=sa.DateTime(timezone=True), type_=sa.DateTime(), existing_nullable=True)
