"""
add org_provider_capabilities table

Revision ID: 20260902_2255
Revises: c2f495a06ed4
Create Date: 2026-09-02 22:55:00.000000

Stage 3 -- Organisation Provider Capability registry (data model + migration).
Additive, reversible, non-destructive: creates only the new
``org_provider_capabilities`` table. No existing table/column/data touched.

Column/constraint DDL below mirrors the SQLAlchemy model metadata exactly
(app/identity/models/organisation_provider_capability.py), which is the
source of truth used by db.create_all() and the synccheck-constraints tool.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260902_2255'
down_revision = 'c2f495a06ed4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'org_provider_capabilities',
        sa.Column('organisation_id', sa.BigInteger(), nullable=False),
        sa.Column('capability_code', sa.String(length=40), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('activated_at', sa.DateTime(), nullable=True),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('meta', sa.JSON(), nullable=False),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organisation_id', 'capability_code', name='uq_org_provider_capability_org_code'),
        sa.CheckConstraint(
            "capability_code IN ('accommodation','transport','events','tourism','venue')",
            name='ck_org_provider_capabilities_capability_code',
        ),
        sa.CheckConstraint(
            "status IN ('intent','activated','suspended','revoked','deactivated')",
            name='ck_org_provider_capabilities_status',
        ),
    )
    op.create_index('ix_org_provider_capability_code_status', 'org_provider_capabilities', ['capability_code', 'status'], unique=False)
    op.create_index('ix_org_provider_capability_org_deleted', 'org_provider_capabilities', ['organisation_id', 'is_deleted'], unique=False)
    op.create_index('ix_org_provider_capabilities_organisation_id', 'org_provider_capabilities', ['organisation_id'], unique=False)
    op.create_index('ix_org_provider_capabilities_is_deleted', 'org_provider_capabilities', ['is_deleted'], unique=False)
    op.create_index('ix_org_provider_capabilities_created_at', 'org_provider_capabilities', ['created_at'], unique=False)
    op.create_index('ix_org_provider_capabilities_updated_at', 'org_provider_capabilities', ['updated_at'], unique=False)


def downgrade() -> None:
    op.drop_table('org_provider_capabilities')
