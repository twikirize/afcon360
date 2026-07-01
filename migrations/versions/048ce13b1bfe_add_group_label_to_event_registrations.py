"""add group_label to event_registrations

Revision ID: 048ce13b1bfe
Revises: 15a1f8d5f2bb
Create Date: 2026-06-12 17:47:16.465788

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '048ce13b1bfe'
down_revision = '15a1f8d5f2bb'
branch_labels = None
depends_on = None


def upgrade():
    # ONLY add group_label - DO NOT drop payment tables
    with op.batch_alter_table('event_registrations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('group_label', sa.String(length=150), nullable=True))
        batch_op.create_index(batch_op.f('ix_event_registrations_group_label'), ['group_label'], unique=False)


def downgrade():
    # Remove group_label column
    with op.batch_alter_table('event_registrations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_event_registrations_group_label'))
        batch_op.drop_column('group_label')