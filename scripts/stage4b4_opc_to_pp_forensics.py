"""
STAGE 4B-4 — OPC -> PP DATA BACKFILL FORENSICS & DRY-RUN (READ-ONLY).

Connects to the configured development database (app default config) and
produces a full READ-ONLY inventory of:

    org_provider_capabilities     (OPC — legacy organisation capability rows)
    provider_participations       (PP  — universal canonical rows)

classifies 1:1 mapping conflicts, and emits a ZERO-WRITE dry-run summary.

This script executes ONLY SELECT statements. It never inserts, updates,
deletes, or alters schema. The actual backfill is a separate, human-gated
operation.

Run:
    & .venv/Scripts/python.exe scripts/stage4b4_opc_to_pp_forensics.py
    & .venv/Scripts/python.exe scripts/stage4b4_opc_to_pp_forensics.py afcon360_test
(optional arg = database name override; defaults to the configured app database)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, text

from app import create_app
from app.identity.models.organisation_provider_capability import (
    ProviderCapabilityCode,
    ProviderCapabilityStatus,
)

VALID_CODES = {c.value for c in ProviderCapabilityCode}
VALID_STATUSES = {s.value for s in ProviderCapabilityStatus}


def q(sql: str, params: dict | None = None) -> int:
    """Run a SELECT that returns a single scalar count/value."""
    with ENGINE.connect() as conn:
        return conn.execute(text(sql), params or {}).scalar()


def rows(sql: str, params: dict | None = None) -> list:
    """Run a SELECT that returns rows (read-only)."""
    with ENGINE.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(text(sql), params or {})]


ENGINE: Any = None


def main() -> int:
    print("=" * 78)
    print("STAGE 4B-4 — OPC -> PP BACKFILL FORENSICS (READ-ONLY)")
    print("Target DB: configured development database (app default config)")
    print("=" * 78)

    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    app = create_app()

    override = sys.argv[1] if len(sys.argv) > 1 else None
    global ENGINE
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if override:
        uri = make_url(uri).set(database=override)
    ENGINE = create_engine(uri)
    print(f"Target database: {make_url(uri).database}")

    with app.app_context():
        insp = inspect(ENGINE)
        has_opc = insp.has_table("org_provider_capabilities")
        has_pp = insp.has_table("provider_participations")
        has_orgs = insp.has_table("organisations")

        print("\n## TABLE PRESENCE")
        print(f"org_provider_capabilities : {has_opc}")
        print(f"provider_participations   : {has_pp}")
        print(f"organisations             : {has_orgs}")

        if not (has_opc and has_pp and has_orgs):
            print("\nBLOCKED: one or more required tables are missing in the "
                  "target database. STOP — do not proceed.")
            return 2

        print("\n## ACTUAL COLUMNS (DB DDL, not model names)")

        def show_cols(table: str) -> None:
            cols = insp.get_columns(table)
            for c in cols:
                print(f"  {table}.{c['name']}: type={c['type']} "
                      f"nullable={c['nullable']} default={c.get('default')}")
            for u in insp.get_unique_constraints(table):
                print(f"  UNIQUE {u['name']}: columns={u['column_names']}")
            for cc in insp.get_check_constraints(table):
                print(f"  CHECK {cc['name']}: {cc['sqltext']!r}")

        show_cols("org_provider_capabilities")
        show_cols("provider_participations")

        print("\n## ROW COUNTS")
        opc_total = q("SELECT count(*) FROM org_provider_capabilities")
        opc_live = q("SELECT count(*) FROM org_provider_capabilities WHERE is_deleted = false")
        opc_deleted = q("SELECT count(*) FROM org_provider_capabilities WHERE is_deleted = true")
        pp_total = q("SELECT count(*) FROM provider_participations")
        pp_individual = q("SELECT count(*) FROM provider_participations WHERE user_id IS NOT NULL")
        pp_org = q("SELECT count(*) FROM provider_participations WHERE organisation_id IS NOT NULL")

        print(f"OPC total                : {opc_total}")
        print(f"OPC non-deleted          : {opc_live}")
        print(f"OPC deleted              : {opc_deleted}")
        print(f"PP total                 : {pp_total}")
        print(f"PP individual rows       : {pp_individual}")
        print(f"PP organisation rows     : {pp_org}")

        print("\n## OPC BY capability_code")
        for r in rows("SELECT capability_code, count(*) AS n "
                      "FROM org_provider_capabilities GROUP BY capability_code ORDER BY 1"):
            print(f"  {r['capability_code']}: {r['n']}")

        print("\n## PP (organisation rows) BY capability_code")
        for r in rows("SELECT capability_code, count(*) AS n "
                      "FROM provider_participations WHERE organisation_id IS NOT NULL "
                      "GROUP BY capability_code ORDER BY 1"):
            print(f"  {r['capability_code']}: {r['n']}")

        print("\n## OPC BY status")
        for r in rows("SELECT status, count(*) AS n "
                      "FROM org_provider_capabilities GROUP BY status ORDER BY 1"):
            print(f"  {r['status']}: {r['n']}")

        print("\n## PP (organisation rows) BY status")
        for r in rows("SELECT status, count(*) AS n FROM provider_participations "
                      "WHERE organisation_id IS NOT NULL GROUP BY status ORDER BY 1"):
            print(f"  {r['status']}: {r['n']}")

        print("\n## ORPHANED ORGANISATION REFERENCES")
        opc_orphans = q(
            "SELECT count(*) FROM org_provider_capabilities o "
            "LEFT JOIN organisations org ON org.id = o.organisation_id "
            "WHERE org.id IS NULL")
        pp_org_orphans = q(
            "SELECT count(*) FROM provider_participations p "
            "LEFT JOIN organisations org ON org.id = p.organisation_id "
            "WHERE p.organisation_id IS NOT NULL AND org.id IS NULL")
        print(f"OPC rows with missing organisation : {opc_orphans}")
        print(f"PP org rows with missing org       : {pp_org_orphans}")

        print("\n## INVALID VALUES")
        if VALID_CODES:
            opc_bad_code = q(
                "SELECT count(*) FROM org_provider_capabilities "
                "WHERE capability_code NOT IN :codes",
                {"codes": tuple(sorted(VALID_CODES))})
            opc_bad_status = q(
                "SELECT count(*) FROM org_provider_capabilities "
                "WHERE status NOT IN :statuses",
                {"statuses": tuple(sorted(VALID_STATUSES))})
            pp_bad_code = q(
                "SELECT count(*) FROM provider_participations "
                "WHERE capability_code NOT IN :codes",
                {"codes": tuple(sorted(VALID_CODES))})
            pp_bad_status = q(
                "SELECT count(*) FROM provider_participations "
                "WHERE status NOT IN :statuses",
                {"statuses": tuple(sorted(VALID_STATUSES))})
            print(f"OPC invalid capability codes : {opc_bad_code}")
            print(f"OPC invalid statuses         : {opc_bad_status}")
            print(f"PP invalid capability codes  : {pp_bad_code}")
            print(f"PP invalid statuses          : {pp_bad_status}")
        else:
            opc_bad_code = opc_bad_status = pp_bad_code = pp_bad_status = 0
            print("  (enum import empty — skipping)")

        print("\n## NULL / MALFORMED VALUES")
        opc_null_org = q("SELECT count(*) FROM org_provider_capabilities WHERE organisation_id IS NULL")
        opc_null_code = q("SELECT count(*) FROM org_provider_capabilities WHERE capability_code IS NULL OR capability_code = ''")
        opc_null_status = q("SELECT count(*) FROM org_provider_capabilities WHERE status IS NULL")
        opc_null_meta = q("SELECT count(*) FROM org_provider_capabilities WHERE meta IS NULL")
        opc_bad_ts = q(
            "SELECT count(*) FROM org_provider_capabilities "
            "WHERE (activated_at IS NOT NULL AND activated_at < created_at) "
            "OR (verified_at IS NOT NULL AND verified_at < created_at) "
            "OR updated_at < created_at")
        print(f"OPC null organisation_id : {opc_null_org}")
        print(f"OPC null/blank code      : {opc_null_code}")
        print(f"OPC null status          : {opc_null_status}")
        print(f"OPC null meta            : {opc_null_meta}")
        print(f"OPC timestamp anomalies  : {opc_bad_ts}")

        print("\n## DUPLICATES (logical key: organisation_id + capability_code)")
        opc_dups = q(
            "SELECT count(*) FROM (SELECT organisation_id, capability_code "
            "FROM org_provider_capabilities GROUP BY 1, 2 HAVING count(*) > 1) d")
        pp_org_dups = q(
            "SELECT count(*) FROM (SELECT organisation_id, capability_code "
            "FROM provider_participations WHERE organisation_id IS NOT NULL "
            "GROUP BY 1, 2 HAVING count(*) > 1) d")
        print(f"OPC duplicate logical rows   : {opc_dups}")
        print(f"PP org duplicate logical rows: {pp_org_dups}")

        print("\n## CONFLICT ANALYSIS (OPC row vs existing PP organisation row)")
        exact_match = q(
            "SELECT count(*) FROM org_provider_capabilities o "
            "WHERE EXISTS (SELECT 1 FROM provider_participations p "
            "WHERE p.organisation_id = o.organisation_id "
            "AND p.capability_code = o.capability_code "
            "AND p.status = o.status AND p.is_deleted = o.is_deleted)")
        state_conflict = q(
            "SELECT count(*) FROM org_provider_capabilities o "
            "WHERE EXISTS (SELECT 1 FROM provider_participations p "
            "WHERE p.organisation_id = o.organisation_id "
            "AND p.capability_code = o.capability_code "
            "AND (p.status <> o.status OR p.is_deleted <> o.is_deleted))")
        print(f"Exact matches (already in PP, same state): {exact_match}")
        print(f"State conflicts (in PP, different state) : {state_conflict}")

        confl_rows = rows(
            "SELECT o.organisation_id, o.capability_code AS code, o.status AS opc_status, "
            "o.is_deleted AS opc_deleted, p.status AS pp_status, p.is_deleted AS pp_deleted "
            "FROM org_provider_capabilities o "
            "JOIN provider_participations p ON p.organisation_id = o.organisation_id "
            "AND p.capability_code = o.capability_code "
            "WHERE p.status <> o.status OR p.is_deleted <> o.is_deleted "
            "ORDER BY 1, 2")
        if confl_rows:
            print("State conflicts detail (org public_id, code, OPC->PP):")
            for r in confl_rows:
                org = rows("SELECT org_id FROM organisations WHERE id = :oid",
                           {"oid": r["organisation_id"]})
                pub = org[0]["org_id"] if org else f"(missing org id={r['organisation_id']})"
                print(f"  {pub} | {r['code']} | {r['opc_status']}/{r['opc_deleted']} -> "
                      f"{r['pp_status']}/{r['pp_deleted']}")
        else:
            print("  (none)")

        print("\n## DRY-RUN SUMMARY (ZERO WRITES)")
        # Rows that would be INSERTED = valid, non-orphan OPC rows with no PP counterpart.
        safe_to_copy = q(
            "SELECT count(*) FROM org_provider_capabilities o "
            "WHERE o.capability_code IN :codes "
            "AND o.status IN :statuses "
            "AND EXISTS (SELECT 1 FROM organisations org WHERE org.id = o.organisation_id) "
            "AND NOT EXISTS (SELECT 1 FROM provider_participations p "
            "WHERE p.organisation_id = o.organisation_id "
            "AND p.capability_code = o.capability_code)",
            {"codes": tuple(sorted(VALID_CODES)), "statuses": tuple(sorted(VALID_STATUSES))})

        print(f"TOTAL OPC rows                 : {opc_total}")
        print(f"SAFE TO COPY (insert into PP)  : {safe_to_copy}")
        print(f"ALREADY PRESENT / EXACT MATCH  : {exact_match}")
        print(f"CONFLICTS (state mismatch)     : {state_conflict}")
        print(f"ORPHANS                        : {opc_orphans}")
        print(f"INVALID CAPABILITIES           : {opc_bad_code}")
        print(f"INVALID STATUSES               : {opc_bad_status}")
        print(f"DUPLICATES                     : {opc_dups}")
        print(f"BLOCKED (orphans+invalid+dup)  : "
              f"{opc_orphans + opc_bad_code + opc_bad_status + opc_dups}")

        sanity = opc_total == safe_to_copy + exact_match + state_conflict
        print(f"\nSanity (total == safe + exact + conflict): {sanity}")

        print("\nREADONLY_OK — no writes were performed.")

    return 0


if __name__ == "__main__":
    try:
        getattr(sys.stdout, "reconfigure", lambda **_: None)(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())