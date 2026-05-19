"""merge_heads

Revision ID: fefed84f1389
Revises: 7d2872a2c358, 20240512_001_create_system_config, add_ota_search_indexes, create_payment_config_tables, create_system_config_table
Create Date: 2026-05-12 16:14:59.714564

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fefed84f1389'
down_revision = ('7d2872a2c358', '20240512_001_create_system_config', 'add_ota_search_indexes', 'create_payment_config_tables', 'create_system_config_table')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
