"""Item 3: prove the atomic inventory UPDATE is a single indexed row update.

Runs EXPLAIN (ANALYZE, BUFFERS) on the exact conditional UPDATE used by
app.events.inventory._atomic_decrement, inside a transaction that is rolled
back so no inventory is changed. The plan must show an Index Scan on
event_ticket_types_pkey touching a single row (no sequential scan, no full
table scan).

    python loadtest/explain_atomic.py
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env(path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_env(PROJECT_ROOT / ".env.testing")
from sqlalchemy import create_engine, text  # noqa: E402

URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
TID = os.getenv("TICKET_TYPE_ID")

engine = create_engine(URL)
with engine.connect() as conn:
    if not TID:
        row = conn.execute(
            text(
                "SELECT id, event_id FROM event_ticket_types "
                "WHERE event_id = (SELECT id FROM events WHERE slug='loadtest-onsale') "
                "LIMIT 1"
            )
        ).first()
        if not row:
            raise SystemExit("No loadtest ticket type found; run staging_server.py first.")
        TID, EID = row
    else:
        EID = conn.execute(
            text("SELECT event_id FROM event_ticket_types WHERE id=:t"),
            {"t": int(TID)},
        ).scalar()

    sql = text(
        "EXPLAIN (ANALYZE, BUFFERS, VERBOSE) "
        "UPDATE event_ticket_types "
        "   SET available_seats = available_seats - 1 "
        " WHERE id = :tid "
        "   AND event_id = :eid "
        "   AND is_active IS TRUE "
        "   AND available_seats >= 1"
    )
    with conn.begin() as tx:
        plan = conn.execute(sql, {"tid": int(TID), "eid": int(EID)}).fetchall()
        tx.rollback()  # do not actually mutate inventory

    print("=" * 70)
    print("ATOMIC_UPDATE_EXPLAIN_ANALYZE (rolled back — no data changed)")
    print(f"ticket_type_id={TID} event_id={EID}")
    print("-" * 70)
    for row in plan:
        print(row[0])
    print("=" * 70)
