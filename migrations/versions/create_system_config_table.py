"""Create system configuration table"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'create_system_config_table'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Create system_configs table
    op.create_table('system_configs',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('key', sa.String(100), nullable=False, unique=True, index=True),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
    )

def downgrade():
    op.drop_table('system_configs')
