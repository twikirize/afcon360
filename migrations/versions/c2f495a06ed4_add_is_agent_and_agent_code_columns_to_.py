"""
add is_agent and agent_code columns to users

Revision ID: c2f495a06ed4
Revises: f91075478868
Create Date: 2026-08-30 22:43:55.122811
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c2f495a06ed4'
down_revision = 'f91075478868'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # agent_float_accounts
    op.create_table(
        'agent_float_accounts',
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False),
        sa.Column('balance', sa.Numeric(precision=20, scale=4), nullable=False, server_default='0'),
        sa.Column('held', sa.Numeric(precision=20, scale=4), nullable=False, server_default='0'),
        sa.Column('last_settled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'currency', name='uq_agent_float_user_currency'),
    )
    op.create_index('ix_agent_float_user', 'agent_float_accounts', ['user_id'], unique=False)

    # agent_float_ledgers
    op.create_table(
        'agent_float_ledgers',
        sa.Column('float_account_id', sa.BigInteger(), nullable=False),
        sa.Column('agent_user_id', sa.BigInteger(), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False),
        sa.Column('amount', sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column('balance_after', sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column('entry_type', sa.String(length=30), nullable=False),
        sa.Column('reference', sa.String(length=64), nullable=True),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['float_account_id'], ['agent_float_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['agent_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('agent_float_ledgers') as batch_op:
        batch_op.create_index('ix_agent_float_ledger_account', ['float_account_id'], unique=False)
        batch_op.create_index('ix_agent_float_ledger_agent', ['agent_user_id'], unique=False)
        batch_op.create_index('ix_agent_float_ledger_created', ['created_at'], unique=False)

    # agent_onboardings
    op.create_table(
        'agent_onboardings',
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('agent_type', sa.String(length=20), nullable=False),
        sa.Column('reference', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='submitted'),
        sa.Column('applicant_data', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('current_stage', sa.String(length=30), nullable=False, server_default='wallet_review'),
        sa.Column('reviewed_by_wallet_admin_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewed_by_compliance_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reference', name='uq_agent_onboardings_reference'),
    )
    with op.batch_alter_table('agent_onboardings') as batch_op:
        batch_op.create_index('ix_agent_onb_user', ['user_id'], unique=False)
        batch_op.create_index('ix_agent_onb_status_stage', ['status', 'current_stage'], unique=False)

    # agent_onboarding_approvals
    op.create_table(
        'agent_onboarding_approvals',
        sa.Column('onboarding_id', sa.BigInteger(), nullable=False),
        sa.Column('stage', sa.String(length=30), nullable=False),
        sa.Column('approver_user_id', sa.BigInteger(), nullable=False),
        sa.Column('approver_role', sa.String(length=50), nullable=False),
        sa.Column('decision', sa.String(length=20), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['approver_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['onboarding_id'], ['agent_onboardings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('agent_onboarding_approvals') as batch_op:
        batch_op.create_index('ix_agent_appr_onb', ['onboarding_id'], unique=False)
        batch_op.create_index('ix_agent_appr_stage', ['stage'], unique=False)

    # add is_agent and agent_code to users
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('is_agent', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('agent_code', sa.String(length=32), nullable=True))
        batch_op.create_index('ix_users_is_agent', ['is_agent'], unique=False)
        batch_op.create_index('ix_users_agent_code', ['agent_code'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_index('ix_users_is_agent')
        batch_op.drop_index('ix_users_agent_code')
        batch_op.drop_column('agent_code')
        batch_op.drop_column('is_agent')

    op.drop_table('agent_onboarding_approvals')
    with op.batch_alter_table('agent_onboardings') as batch_op:
        batch_op.drop_index('ix_agent_onb_status_stage')
        batch_op.drop_index('ix_agent_onb_user')
    op.drop_table('agent_onboardings')

    op.drop_table('agent_float_ledgers')
    with op.batch_alter_table('agent_float_accounts') as batch_op:
        batch_op.drop_index('ix_agent_float_user')
    op.drop_table('agent_float_accounts')