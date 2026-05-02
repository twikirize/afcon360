"""Fix compliance tables to use BigInteger for all ID columns

Revision ID: fix_compliance_bigint_types
Revises: 1e93a437d0e6
Create Date: 2026-04-29 22:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'fix_compliance_bigint_types'
down_revision = '56cf92e4fdef'  # Depend on compliance models
branch_labels = None
depends_on = None


def upgrade():
    # Fix compliance_cases table - change id from Integer to BigInteger
    with op.batch_alter_table('compliance_cases', schema=None) as batch_op:
        # Foreign keys referencing this table need to be dropped first
        batch_op.alter_column('id',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=False,
                              autoincrement=True)
        # Fix foreign key columns
        batch_op.alter_column('user_id',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=True)
        batch_op.alter_column('organisation_id',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=True)
        batch_op.alter_column('assigned_to',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=True)
        batch_op.alter_column('resolved_by',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=True)
        batch_op.alter_column('created_by',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=False)
        batch_op.alter_column('escalated_from',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=True)
        batch_op.alter_column('kyc_id',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=True)
        batch_op.alter_column('payout_id',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=True)
        batch_op.alter_column('flag_id',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=True)

    # Fix data_subject_requests table
    with op.batch_alter_table('data_subject_requests', schema=None) as batch_op:
        batch_op.alter_column('id',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=False,
                              autoincrement=True)
        batch_op.alter_column('user_id',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=False)
        batch_op.alter_column('verified_by',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=True)
        batch_op.alter_column('assigned_to',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=True)
        batch_op.alter_column('created_by',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=False)

    # Fix compliance_reports table
    with op.batch_alter_table('compliance_reports', schema=None) as batch_op:
        batch_op.alter_column('id',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=False,
                              autoincrement=True)
        batch_op.alter_column('reviewed_by',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=True)
        batch_op.alter_column('approved_by',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=True)
        batch_op.alter_column('created_by',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=False)

    # Fix compliance_settings table
    with op.batch_alter_table('compliance_settings', schema=None) as batch_op:
        batch_op.alter_column('id',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=False,
                              autoincrement=True)

    # Fix compliance_audit_logs table
    with op.batch_alter_table('compliance_audit_logs', schema=None) as batch_op:
        batch_op.alter_column('id',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=False,
                              autoincrement=True)
        batch_op.alter_column('decided_by',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=True)

    # Fix content_flags table - compliance_case_id foreign key
    with op.batch_alter_table('content_flags', schema=None) as batch_op:
        batch_op.alter_column('compliance_case_id',
                              existing_type=sa.Integer(),
                              type_=sa.BigInteger(),
                              existing_nullable=True)


def downgrade():
    # Revert changes - downgrade not recommended for type changes with data
    pass
