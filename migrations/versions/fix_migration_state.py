"""Mark migrations as applied"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'fix_migration_state'
down_revision = '1e93a437d0e6'
branch_labels = None
depends_on = None

def upgrade():
    # This migration exists only to mark the previous one as applied
    pass

def downgrade():
    pass
