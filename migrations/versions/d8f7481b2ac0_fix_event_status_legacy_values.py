from alembic import op


revision = 'd8f7481b2ac0'
down_revision = '7053dc695af1'
branch_labels = None
depends_on = None


def upgrade():
    # normalize legacy statuses
    op.execute("""
        UPDATE events
        SET status = 'published'
        WHERE status IN ('active', 'live');
    """)

    op.execute("""
        UPDATE events
        SET status = 'pending_approval'
        WHERE status = 'pending';
    """)

    # safety net: force invalid values to draft
    op.execute("""
        UPDATE events
        SET status = 'draft'
        WHERE status NOT IN (
            'draft','pending_approval','approved','rejected',
            'published','suspended','paused','cancelled',
            'archived','deleted'
        );
    """)


def downgrade():
    op.execute("""
        UPDATE events
        SET status = 'active'
        WHERE status = 'published';
    """)