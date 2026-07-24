"""make organisations compliance_case_id FK deferrable

Revision ID: 20260718_1951
Revises: 586b35d32d53
Create Date: 2026-07-18 19:51:26.141601

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260718_1951'
down_revision = '586b35d32d53'
branch_labels = None
depends_on = None


def upgrade():
    # organisations.compliance_case_id references compliance_cases.id, while
    # compliance_cases.organisation_id references organisations.id — a direct
    # bidirectional FK cycle. Making this side DEFERRABLE INITIALLY DEFERRED
    # breaks the sort cycle for Alembic (removes the SAWarning about
    # unresolvable cycles between compliance_cases/organisations) and lets
    # rows be inserted in either order. PostgreSQL only.
    op.execute(
        "ALTER TABLE organisations "
        "DROP CONSTRAINT organisations_compliance_case_id_fkey"
    )
    op.execute(
        "ALTER TABLE organisations "
        "ADD CONSTRAINT organisations_compliance_case_id_fkey "
        "FOREIGN KEY (compliance_case_id) REFERENCES compliance_cases (id) "
        "DEFERRABLE INITIALLY DEFERRED"
    )


def downgrade():
    op.execute(
        "ALTER TABLE organisations "
        "DROP CONSTRAINT organisations_compliance_case_id_fkey"
    )
    op.execute(
        "ALTER TABLE organisations "
        "ADD CONSTRAINT organisations_compliance_case_id_fkey "
        "FOREIGN KEY (compliance_case_id) REFERENCES compliance_cases (id)"
    )
