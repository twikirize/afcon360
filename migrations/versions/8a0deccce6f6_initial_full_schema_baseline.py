"""initial_full_schema_baseline

Single, complete ROOT migration that builds the entire AFCON360 schema from
the current SQLAlchemy models. It replaces the previous broken baseline
(ab6dd422c152_initial_schema, now retired under migrations/_retired_versions/)
which never created users/events/accounts/transactions/accommodation_properties,
so `flask db upgrade` could not build a database from scratch in ANY environment.

We build via SQLAlchemy's ``metadata.create_all()`` (the same proven path used
by scripts/setup_test_db_schema.py). ``create_all()`` orders tables
topologically and defers circular foreign keys via ALTER statements, so a
from-scratch build succeeds everywhere: production, staging, and brand-new
environments.

Revision ID: 8a0deccce6f6
Revises:
Create Date: 2026-08-20 21:21:34.793318

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8a0deccce6f6'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Build the full schema from the current models. create_all() resolves
    # table/FK ordering (including circular dependencies) automatically, which
    # is exactly what `flask db upgrade` from an empty database requires.
    from app.extensions import db
    db.metadata.create_all(op.get_bind())


def downgrade():
    from app.extensions import db
    db.metadata.drop_all(op.get_bind())
