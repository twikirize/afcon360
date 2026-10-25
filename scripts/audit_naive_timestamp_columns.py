"""Read-only inventory of PostgreSQL timestamp columns for timezone rollout.

Set AFCON360_TIMEZONE_AUDIT_DATABASE_URL explicitly to the exact target
database URL. No schema or row writes are performed. The report deliberately
does not infer the historical timezone of naive values; that requires evidence
from the owning application path.
"""

from __future__ import annotations

import json
import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


SQL = text(
    """
    SELECT
        n.nspname AS schema_name,
        c.relname AS table_name,
        a.attname AS column_name,
        pg_catalog.format_type(a.atttypid, a.atttypmod) AS postgres_type,
        a.attnotnull AS not_null,
        pg_get_expr(d.adbin, d.adrelid) AS column_default,
        c.reltuples::bigint AS estimated_rows
    FROM pg_catalog.pg_class AS c
    JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
    JOIN pg_catalog.pg_attribute AS a ON a.attrelid = c.oid
    LEFT JOIN pg_catalog.pg_attrdef AS d
        ON d.adrelid = c.oid AND d.adnum = a.attnum
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p')
      AND NOT c.relispartition
      AND a.attnum > 0
      AND NOT a.attisdropped
      AND pg_catalog.format_type(a.atttypid, a.atttypmod)
          IN ('timestamp without time zone', 'timestamp with time zone')
    ORDER BY n.nspname, c.relname, a.attnum
    """
)


def main() -> int:
    url = os.environ.get("AFCON360_TIMEZONE_AUDIT_DATABASE_URL")
    if not url:
        print(
            "ERROR: Set AFCON360_TIMEZONE_AUDIT_DATABASE_URL to the specific "
            "database to audit. No connection attempted.",
            file=sys.stderr,
        )
        return 2

    try:
        parsed = make_url(url)
    except Exception as exc:
        print(f"ERROR: invalid database URL ({type(exc).__name__})", file=sys.stderr)
        return 2

    print(
        f"Target: host={parsed.host or '(local/default)'} "
        f"port={parsed.port or '(default)'} database={parsed.database!r} "
        f"user={parsed.username!r}"
    )
    # Fail closed on a name that looks production-like unless the operator
    # separately opts in to a read-only audit. The script remains SELECT-only.
    prod_name = "prod" in (parsed.database or "").lower()
    allow_prod = os.environ.get("AFCON360_ALLOW_PROD_TIMEZONE_READ_ONLY_AUDIT") == "YES"
    if prod_name and not allow_prod:
        print(
            "ERROR: target database name looks production-like. A separate "
            "explicit read-only audit authorization is required.",
            file=sys.stderr,
        )
        return 3

    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={
            "options": "-c timezone=UTC -c statement_timeout=30000 "
            "-c default_transaction_read_only=on"
        },
    )
    try:
        with engine.connect() as conn:
            # Catalog and setting queries are executed inside an explicit
            # read-only transaction; no row ranges are scanned.
            conn.exec_driver_sql("BEGIN READ ONLY")
            try:
                identity = conn.execute(
                    text(
                        "SELECT current_database() AS database_name, "
                        "current_setting('TimeZone') AS session_timezone, "
                        "version() AS server_version"
                    )
                ).mappings().one()
                rows = conn.execute(SQL).mappings().all()
                naive = [r for r in rows if r["postgres_type"] == "timestamp without time zone"]
                aware = [r for r in rows if r["postgres_type"] == "timestamp with time zone"]
                report = {
                    "mode": "READ ONLY — catalog metadata only; no row scans",
                    "database": dict(identity),
                    "timestamp_column_count": len(rows),
                    "timezone_aware_column_count": len(aware),
                    "timezone_naive_column_count": len(naive),
                    "naive_columns": [dict(r) for r in naive],
                    "aware_columns": [dict(r) for r in aware],
                    "warning": (
                        "A catalog report does not prove the historical timezone "
                        "of stored naive values. Confirm writer semantics and row "
                        "history before authorizing conversion."
                    ),
                }
                print(json.dumps(report, indent=2, default=str))
            finally:
                conn.exec_driver_sql("ROLLBACK")
    except Exception as exc:
        print(
            f"ERROR: read-only timezone audit failed "
            f"({type(exc).__name__}): {exc}",
            file=sys.stderr,
        )
        return 4
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
