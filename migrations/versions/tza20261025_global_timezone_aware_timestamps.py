"""Convert legacy naive application timestamps to UTC-aware PostgreSQL timestamps.

Revision ID: tza20261025
Revises: 1792869659
Create Date: 2026-10-25

SAFETY:
This is a schema-wide, table-rewriting migration and may take strong locks.
It must not run until read-only per-database evidence establishes the
interpretation of legacy naive values. It fails closed unless the operator
explicitly sets AFCON360_LEGACY_NAIVE_TIMESTAMPS_ARE_UTC=YES after that audit.

Conversion semantics: each existing naive value is interpreted as UTC via
(col AT TIME ZONE 'UTC'); this preserves the stored wall-clock value as the
intended UTC instant. It is NOT safe for values historically stored as local
wall-clock time or with mixed conventions.
"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa


revision = "tza20261025"
down_revision = "1792869659"
branch_labels = None
depends_on = None


def _naive_timestamp_columns(connection):
    """Return application-table timestamp columns without timezone."""
    return connection.execute(
        sa.text(
            """
            SELECT
                n.nspname AS schema_name,
                c.relname AS table_name,
                a.attname AS column_name,
                pg_get_expr(d.adbin, d.adrelid) AS column_default
            FROM pg_catalog.pg_class AS c
            JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
            JOIN pg_catalog.pg_attribute AS a ON a.attrelid = c.oid
            JOIN pg_catalog.pg_type AS t ON t.oid = a.atttypid
            LEFT JOIN pg_catalog.pg_attrdef AS d
                ON d.adrelid = c.oid AND d.adnum = a.attnum
            WHERE n.nspname = 'public'
              AND c.relkind IN ('r', 'p')
              AND NOT c.relispartition
              AND a.attnum > 0
              AND NOT a.attisdropped
              AND a.attgenerated = ''
              AND t.typname = 'timestamp'
              AND pg_catalog.format_type(a.atttypid, a.atttypmod)
                    = 'timestamp without time zone'
            ORDER BY n.nspname, c.relname, a.attnum
            """
        )
    ).mappings().all()


def upgrade():
    if os.environ.get("AFCON360_LEGACY_NAIVE_TIMESTAMPS_ARE_UTC") != "YES":
        raise RuntimeError(
            "Timezone migration refused. First complete the read-only "
            "column/data audit for this exact database and verify every "
            "legacy naive timestamp is UTC. Then explicitly set "
            "AFCON360_LEGACY_NAIVE_TIMESTAMPS_ARE_UTC=YES. This migration "
            "rewrites timestamp columns and can take strong table locks."
        )

    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        raise RuntimeError("The UTC timestamp migration supports PostgreSQL only.")

    # Database expressions and casts in this migration must use UTC too.
    op.execute("SET LOCAL TIME ZONE 'UTC'")

    rows = _naive_timestamp_columns(connection)
    preparer = connection.dialect.identifier_preparer

    for row in rows:
        schema = preparer.quote(row["schema_name"])
        table = preparer.quote(row["table_name"])
        column = preparer.quote(row["column_name"])
        qualified_table = f"{schema}.{table}"
        default = row["column_default"]

        # Dropping/restoring the server default avoids PostgreSQL rejecting
        # some defaults during a column type conversion.
        if default is not None:
            op.execute(
                sa.text(
                    f"ALTER TABLE {qualified_table} "
                    f"ALTER COLUMN {column} DROP DEFAULT"
                )
            )

        op.execute(
            sa.text(
                f"ALTER TABLE {qualified_table} "
                f"ALTER COLUMN {column} TYPE TIMESTAMP WITH TIME ZONE "
                f"USING {column} AT TIME ZONE 'UTC'"
            )
        )

        if default is not None:
            op.execute(
                sa.text(
                    f"ALTER TABLE {qualified_table} "
                    f"ALTER COLUMN {column} SET DEFAULT {default}"
                )
            )


def downgrade():
    # At upgrade time, this migration discovers columns dynamically. Without
    # preserving the exact pre-upgrade column inventory, converting every
    # timestamp-with-time-zone column back would also damage columns that were
    # already timezone-aware before this migration. Fail closed rather than
    # perform that unsafe blanket reversal.
    raise RuntimeError(
        "Automatic downgrade is intentionally disabled for this discovery-based "
        "timezone migration. Restore the verified pre-migration snapshot or "
        "prepare a reviewed reverse migration from the captured preflight inventory."
    )
