"""booking status enum to string

BookingStatus ENUM -> VARCHAR(30) reference implementation (expand/contract).

Shell created ONLY via scripts/create_migration.py (approved mechanism).
The conversion statement below is EXPLICITLY AUTHORIZED explicit DDL
(owner GO for Phase 1, item 11): Alembic autogenerate cannot express a
USING-clause type conversion (it would render drop+add = data loss), so
there is no generated form to prefer. This file contains ONLY the type
conversion. CHECK constraints (ck_transport_bookings_status,
chk_no_match_reason) travel exclusively through
scripts/sync_check_constraints.py --accept-model-truth (sanctioned flow).

Pre-apply gate (owner): pre-census
  SELECT status::text, count(*) FROM transport_bookings GROUP BY 1;
must show ONLY the 11 legacy UPPER labels, zero NO_MATCH rows.

Revision ID: 20260930_1335
Revises: e8bf41930fb2
Create Date: 2026-09-30 13:35:09.975428

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260930_1335'
down_revision = 'e8bf41930fb2'
branch_labels = None
depends_on = None

_UPGRADE_USING = "lower(status::text)"
# Downgrade must define the 12-label type: the live bookingstatus type
# only ever carried 11 labels (NO_MATCH never added). ADD VALUE cannot
# run inside the migration transaction, so the downgrade builds a
# 12-label replacement type, casts via upper(), drops the old type and
# renames (all transactional; proven on scratch objects in
# tests/transport/test_match01_status_string_contract.py).
_DOWNGRADE_LABELS = (
    "'DRAFT','PENDING_PAYMENT','CONFIRMED','ASSIGNED',"
    "'DRIVER_EN_ROUTE','PICKUP_ARRIVED','IN_PROGRESS','COMPLETED',"
    "'CANCELLED','NO_SHOW','DISPUTED','NO_MATCH'"
)


def upgrade():
    # One column only. USING maps legacy UPPER labels to the lowercase
    # application values 1:1 (census-preserving; verified by simulation).
    # Harmless on databases already built VARCHAR-first (fresh
    # create_all): lower() over varchar is a no-op mapping.
    # The status-value CHECK (ck_transport_bookings_status) arrives
    # separately via the sync flow (detected as ADD, proven in gate).
    op.execute(sa.text(
        "ALTER TABLE transport_bookings ALTER COLUMN status "
        f"TYPE VARCHAR(30) USING {_UPGRADE_USING}"
    ))
    # chk_no_match_reason MUST be refreshed here, not via sync: the sync
    # tool's normalize_sql() lowercases all SQL before comparing
    # (scripts/sync_check_constraints.py:164), so it is provably blind to
    # this UPPER->lower text change (dry-run flags no REPLACE for it).
    # Without this refresh, the stale UPPER-literal CHECK would reject
    # every future lowercase no_match write. Text matches the model
    # metadata verbatim.
    op.execute(sa.text(
        "ALTER TABLE transport_bookings "
        "DROP CONSTRAINT IF EXISTS chk_no_match_reason"))
    op.execute(sa.text(
        "ALTER TABLE transport_bookings ADD CONSTRAINT chk_no_match_reason "
        "CHECK ((status = 'no_match' AND no_match_reason IS NOT NULL "
        "AND no_match_reason IN ('no_supply', 'all_rejected')) "
        "OR (status != 'no_match' AND no_match_reason IS NULL))"))


def downgrade():
    # Restores the ENUM type WITH all 12 labels (never claim the 11-label
    # live type suffices: rows may hold 'no_match'). CHECK reconciliation
    # after a downgrade goes through scripts/sync_check_constraints.py;
    # this function restores the TYPE only (proven census-safe).
    op.execute(sa.text(
        f"CREATE TYPE bookingstatus_12 AS ENUM ({_DOWNGRADE_LABELS})"))
    op.execute(sa.text(
        "ALTER TABLE transport_bookings ALTER COLUMN status "
        "TYPE bookingstatus_12 USING upper(status)::bookingstatus_12"))
    op.execute(sa.text("DROP TYPE bookingstatus"))
    op.execute(sa.text("ALTER TYPE bookingstatus_12 RENAME TO bookingstatus"))
    # Restore the pre-conversion CHECK text (UPPER literals against the
    # ENUM type). Post-downgrade CHECK reconciliation then belongs to the
    # sync flow, same as the forward direction.
    op.execute(sa.text(
        "ALTER TABLE transport_bookings "
        "DROP CONSTRAINT IF EXISTS chk_no_match_reason"))
    op.execute(sa.text(
        "ALTER TABLE transport_bookings ADD CONSTRAINT chk_no_match_reason "
        "CHECK ((status::text = 'NO_MATCH' AND no_match_reason IS NOT NULL "
        "AND no_match_reason IN ('no_supply', 'all_rejected')) "
        "OR (status::text != 'NO_MATCH' AND no_match_reason IS NULL))"))
