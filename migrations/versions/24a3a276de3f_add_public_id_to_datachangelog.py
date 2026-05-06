"""Add public_id to DataChangeLog for IDGuard compliance

Revision ID: 24a3a276de3f
Revises: e7c5932521a3
Create Date: 2026-05-06 14:23:09.204285
"""
from alembic import op
import sqlalchemy as sa
import uuid

# revision identifiers, used by Alembic.
revision = '24a3a276de3f'
down_revision = 'e7c5932521a3'
branch_labels = None
depends_on = None

def upgrade():
    # Add public_id column (nullable initially)
    op.add_column('data_change_logs', 
        sa.Column('public_id', sa.String(36), nullable=True)
    )
    
    # Generate UUIDs for existing rows using Python
    conn = op.get_bind()
    import uuid
    
    # Get all rows without public_id
    result = conn.execute(sa.text(
        "SELECT id FROM data_change_logs WHERE public_id IS NULL"
    ))
    
    for row in result:
        new_uuid = str(uuid.uuid4())
        conn.execute(
            sa.text("UPDATE data_change_logs SET public_id = :uuid WHERE id = :id"),
            {"uuid": new_uuid, "id": row[0]}
        )
    
    # Now make it NOT NULL
    op.alter_column('data_change_logs', 'public_id', 
                    existing_type=sa.String(36),
                    nullable=False)
    
    # Create unique index
    op.create_index('idx_dc_public_id', 'data_change_logs', ['public_id'], unique=True)

def downgrade():
    op.drop_index('idx_dc_public_id', table_name='data_change_logs')
    op.drop_column('data_change_logs', 'public_id')
