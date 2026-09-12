"""DB row-tracking isolation for test lifecycle.

Tracks rows inserted during each test and cleans them up at teardown,
eliminating cross-test pollution from committed data.

Design:
- The test DB is shared and persists across RUNS. Cleanup restores every
  table to its session-start state after each test, so the schema's
  "dirty" (has rows) / "empty" classification is stable for the session.
  Because of that, a single baseline captured ONCE per session is valid for
  every per-test cleanup:
    - int PK tables   -> session-start (count, max(id))
    - UUID PK tables  -> session-start set of ids
    - other/composite -> session-start canonical row set
    - empty tables    -> "was empty" marker (cleanup = DELETE ALL rows,
                         since any row found there is test-created)
- Cleanup DELETE:
    - int table       -> DELETE WHERE id > baseline max
    - uuid table      -> DELETE rows whose id NOT in baseline set
    - other tables    -> DELETE each current row not in baseline set
    - empty table     -> DELETE ALL
  FK-safe delete order is computed once from a cached FK graph.
- Baseline is lazily computed on the first test (before ANY test inserts),
  so fixture-created rows (test_user, test_admin, ...) are captured as
  post-baseline and cleaned up like any other test data.

PK strategies (per table):
  - integer PK     -> (count, max(id); rows with id > max are test-created)
  - UUID PK        -> exact pre-existing ID set
  - composite PK   -> full-row snapshot (row equality)
  - no PK          -> full-row snapshot (row equality)

This is the "Option B — Row tracking + explicit cleanup" architecture.
"""

import json
import threading
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy import inspect as sa_inspect, text


# ---------------------------------------------------------------------------
# Topological sort for FK-safe delete ordering
# ---------------------------------------------------------------------------

def build_fk_graph(engine) -> Dict[str, List[str]]:
    """Build a foreign-key dependency graph for all public tables.

    Returns {table: [referred_tables]} — i.e. which tables this table
    depends on via FK.

    Only FKs that actually BLOCK the deletion of their referred (parent)
    row impose deleting-order constraints and are included:

      - ondelete is a no-op / NO ACTION / RESTRICT  -> included
      - ondelete CASCADE / SET NULL / SET DEFAULT   -> excluded (the
        database handles the referenced-row removal automatically)
      - deferrable + initially deferred             -> excluded (checked
        at COMMIT; the per-test cleanup deletes every test-created row in
        a single transaction, so the constraint is satisfied regardless of
        deletion order)

    Excluding the non-blocking edges keeps the graph acyclic in practice
    (e.g. the ``users`` <-> ``organisations`` <-> ``compliance_cases``
    mutual-FK cycle dissolves: every edge in that SCC is either SET NULL or
    deferred), so ``topological_delete_order`` returns a valid,
    dependents-before-parents order instead of a cycle-skipped guess.
    """
    inspector = sa_inspect(engine)
    graph: Dict[str, List[str]] = {}
    table_names = inspector.get_table_names()
    for table_name in table_names:
        if table_name.startswith("_") or table_name == "alembic_version":
            continue
        referred = []
        try:
            fks = inspector.get_foreign_keys(table_name)
        except Exception:
            fks = []
        for fk in fks:
            parent = fk.get("referred_table")
            if not parent or parent not in table_names:
                continue
            options = fk.get("options") or {}
            ondelete = (options.get("ondelete") or "NO ACTION").upper()
            if ondelete in ("CASCADE", "SET NULL", "SET DEFAULT"):
                continue  # parent-row removal is automatically handled
            if options.get("deferrable") and (options.get("initially") or "").upper() == "DEFERRED":
                continue  # checked at COMMIT; single-txn cleanup is order-safe
            referred.append(parent)
        graph[table_name] = referred
    return graph


def topological_delete_order(fk_graph: Dict[str, List[str]]) -> List[str]:
    """Return tables in DELETION-safe order (dependents before parents).

    If table A has an FK to table B, A is deleted first.
    Handles cycles gracefully by falling back to insertion order.

    This is the reverse of topological insertion order: children are
    visited first so that dependent rows are removed before parent rows.
    """
    visited: Set[str] = set()
    in_stack: Set[str] = set()
    order: List[str] = []

    def _visit(table: str):
        if table in visited:
            return
        if table in in_stack:
            # cycle detected — break it by skipping
            return
        in_stack.add(table)
        for dep in fk_graph.get(table, []):
            if dep != table:  # skip self-references
                _visit(dep)
        in_stack.discard(table)
        visited.add(table)
        order.append(table)

    for table in fk_graph:
        _visit(table)

    # Reverse: standard topo sort gives dependency-before-child (insertion
    # order).  For deletion we need child-before-dependency order.
    return list(reversed(order))


# ---------------------------------------------------------------------------
# Table snapshot helpers
# ---------------------------------------------------------------------------

_TABLE_SKIP_PREFIXES = ("_",)
_TABLE_SKIP_NAMES = {"alembic_version", "_test_rows"}


def _get_fk_columns(inspector, table_name: str) -> List[str]:
    """Return FK column names that can block parent-row deletion.

    Excludes CASCADE / SET NULL / SET DEFAULT (Postgres handles those) and
    deferrable-deferred FKs. Only NO ACTION / RESTRICT columns are returned.
    """
    try:
        fks = inspector.get_foreign_keys(table_name)
    except Exception:
        return []
    cols: List[str] = []
    for fk in fks:
        options = fk.get("options") or {}
        ondelete = (options.get("ondelete") or "NO ACTION").upper()
        if ondelete in ("CASCADE", "SET NULL", "SET DEFAULT"):
            continue
        if options.get("deferrable") and (options.get("initially") or "").upper() == "DEFERRED":
            continue
        for c in fk.get("constrained_columns", []):
            if c not in cols:
                cols.append(c)
    return cols


def _get_pk_columns(inspector, table_name: str) -> List[str]:
    """Return ordered PK column names for a table."""
    try:
        pk = inspector.get_pk_constraint(table_name)
        return pk.get("constrained_columns", [])
    except Exception:
        return []


def snapshot_table_rows_readonly(conn, table_name: str) -> Dict[str, Any]:
    """Snapshot a table using a dedicated connection (no ORM session).

    Identical semantics to :func:`snapshot_table_rows` but executes against a
    raw ``Connection`` so the ORM identity map is never expired by the
    snapshot reads. ``conn`` must provide its engine via ``conn.engine``.
    """
    inspector = sa_inspect(conn.engine)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    pk_cols = _get_pk_columns(inspector, table_name)
    fk_cols = _get_fk_columns(inspector, table_name)

    result = conn.execute(text(f'SELECT * FROM "{table_name}"'))
    all_rows = [tuple(row) for row in result]

    snap: Dict[str, Any] = {
        "columns": columns,
        "pk_columns": pk_cols,
        "count": len(all_rows),
    }

    if not pk_cols or len(pk_cols) > 2:
        snap["pk_type"] = "composite" if len(pk_cols) > 2 else "none"
        if not all_rows:
            return snap
        snap["row_snap"] = all_rows
        return snap

    if len(pk_cols) == 1:
        pk_col = pk_cols[0]
        pk_idx = columns.index(pk_col) if pk_col in columns else None
        if pk_idx is None:
            snap["pk_type"] = "none"
            if not all_rows:
                return snap
            snap["row_snap"] = all_rows
            return snap

        values = [row[pk_idx] for row in all_rows]
        sample = values[0] if values else None

        if sample is not None and isinstance(sample, int):
            snap["pk_type"] = "int"
            snap["max_pk"] = max(values) if values else 0
            if fk_cols:
                fk_idx_map = {fc: columns.index(fc) for fc in fk_cols if fc in columns}
                if fk_idx_map:
                    snap["fk_columns"] = list(fk_idx_map.keys())
                    snap["fk_baseline"] = {
                        row[pk_idx]: {fc: row[idx] for fc, idx in fk_idx_map.items()}
                        for row in all_rows
                    }
        elif sample is not None and (
            isinstance(sample, str) and len(sample) == 36
            or isinstance(sample, UUID)
        ):
            snap["pk_type"] = "uuid"
            snap["uuid_pks"] = {str(v) if isinstance(v, UUID) else v for v in values}
            if fk_cols:
                fk_idx_map = {fc: columns.index(fc) for fc in fk_cols if fc in columns}
                if fk_idx_map:
                    snap["fk_columns"] = list(fk_idx_map.keys())
                    snap["fk_baseline"] = {
                        (str(row[pk_idx]) if isinstance(row[pk_idx], UUID) else row[pk_idx]):
                            {fc: row[idx] for fc, idx in fk_idx_map.items()}
                        for row in all_rows
                    }
        else:
            snap["pk_type"] = "other"
            if not all_rows:
                return snap
            snap["row_snap"] = all_rows
        return snap

    # Composite PK (2 columns)
    snap["pk_type"] = "composite"
    if not all_rows:
        return snap
    snap["row_snap"] = all_rows
    return snap


# ---------------------------------------------------------------------------
# Cleanup logic
# ---------------------------------------------------------------------------

def revert_fk_mutations(conn, table_name: str, snap: Dict[str, Any]) -> int:
    """Restore FK columns on pre-existing rows to their session-start values.

    Runs BEFORE cleanup_table's delete pass, so removing a test-created parent
    cannot orphan a pre-existing child that was repointed mid-test.
    """
    from sqlalchemy import bindparam

    fk_baseline = snap.get("fk_baseline") or {}
    fk_columns = snap.get("fk_columns") or []
    pk_cols = snap.get("pk_columns") or []
    if not fk_baseline or not fk_columns or len(pk_cols) != 1:
        return 0

    pk_col = pk_cols[0]
    pk_type = snap.get("pk_type")
    cols_sql = ", ".join(f'"{c}"' for c in [pk_col, *fk_columns])

    if pk_type == "int":
        max_pk = snap.get("max_pk", 0)
        if max_pk == 0:
            return 0
        rows = conn.execute(
            text(f'SELECT {cols_sql} FROM "{table_name}" WHERE "{pk_col}" <= :max_pk'),
            {"max_pk": max_pk},
        ).all()
    elif pk_type == "uuid":
        uuid_pks = list(snap.get("uuid_pks") or set())
        if not uuid_pks:
            return 0
        stmt = text(
            f'SELECT {cols_sql} FROM "{table_name}" WHERE "{pk_col}" IN :pks'
        ).bindparams(bindparam("pks", expanding=True))
        rows = conn.execute(stmt, {"pks": uuid_pks}).all()
    else:
        return 0

    reverted = 0
    for row in rows:
        pk_val = row[0]
        key = str(pk_val) if isinstance(pk_val, UUID) else pk_val
        baseline = fk_baseline.get(key)
        if baseline is None:
            continue
        for i, col in enumerate(fk_columns, start=1):
            baseline_val = baseline.get(col)
            if row[i] != baseline_val:
                conn.execute(
                    text(f'UPDATE "{table_name}" SET "{col}" = :v WHERE "{pk_col}" = :pk'),
                    {"v": baseline_val, "pk": pk_val},
                )
                reverted += 1
    return reverted


def cleanup_table(session, table_name: str, snap: Dict[str, Any]) -> int:
    """Delete rows inserted during the test. Returns count deleted.

    A stronger-than-necessary delete is fine for tables that started empty
    (``pre_count == 0`` or no baseline rows): exactly the rows removed were
    test-created, so we remove every row currently present.
    """
    pk_type = snap.get("pk_type", "none")

    if pk_type == "int":
        max_pk = snap.get("max_pk", 0)
        if max_pk == 0:
            # Table was empty before the test — delete everything.
            result = session.execute(text(f'DELETE FROM "{table_name}"'))
            return result.rowcount
        pk_col = snap["pk_columns"][0]
        result = session.execute(
            text(f'DELETE FROM "{table_name}" WHERE "{pk_col}" > :max_pk'),
            {"max_pk": max_pk},
        )
        return result.rowcount

    if pk_type == "uuid":
        existing = snap.get("uuid_pks", set())
        if not existing:
            # table was empty before test — delete everything
            result = session.execute(text(f'DELETE FROM "{table_name}"'))
            return result.rowcount
        pk_col = snap["pk_columns"][0]
        # delete rows whose PK is NOT in the snapshot
        rows = session.execute(text(f'SELECT "{pk_col}" FROM "{table_name}"'))
        current_ids = {
            str(row[0]) if isinstance(row[0], UUID) else row[0] for row in rows
        }
        to_delete = current_ids - existing
        if not to_delete:
            return 0
        # batch delete (PostgreSQL IN limit is ~32767 params)
        deleted = 0
        batch_size = 1000
        id_list = list(to_delete)
        for i in range(0, len(id_list), batch_size):
            batch = id_list[i : i + batch_size]
            placeholders = ", ".join(f":id{j}" for j in range(len(batch)))
            params = {f"id{j}": v for j, v in enumerate(batch)}
            result = session.execute(
                text(f'DELETE FROM "{table_name}" WHERE "{pk_col}" IN ({placeholders})'),
                params,
            )
            deleted += result.rowcount
        return deleted

    if pk_type in ("none", "composite", "other"):
        row_snap = snap.get("row_snap", [])
        if not row_snap:
            # Table was empty before the test — delete everything.
            result = session.execute(text(f'DELETE FROM "{table_name}"'))
            return result.rowcount
        existing_set = {_canonical_row(r) for r in row_snap}
        rows = session.execute(text(f'SELECT * FROM "{table_name}"'))
        current_rows = [tuple(row) for row in rows]
        to_delete = [r for r in current_rows if _canonical_row(r) not in existing_set]
        if not to_delete:
            return 0
        # Fallback row-equality deletes. Serialize every column via ::text so
        # JSON/JSONB values (returned as dicts) work reliably as params.
        deleted = 0
        for row in to_delete:
            conditions = []
            params = {}
            for i, val in enumerate(row):
                col_name = snap["columns"][i]
                param_name = f"v{i}"
                if val is None:
                    conditions.append(f'"{col_name}" IS NULL')
                else:
                    conditions.append(f'"{col_name}"::text = :{param_name}')
                    params[param_name] = str(val)
            where = " AND ".join(conditions)
            result = session.execute(
                text(f'DELETE FROM "{table_name}" WHERE {where}'), params
            )
            deleted += result.rowcount
        return deleted

    return 0


def _canonical_row(row) -> Tuple[str, ...]:
    """Hashable, stable representation of a row for equality comparison.

    Handles JSON/JSONB values (dicts/lists) and UUIDs uniformly.
    """
    parts = []
    for val in row:
        if val is None:
            parts.append("NULL")
        elif isinstance(val, (dict, list)):
            parts.append(json.dumps(val, sort_keys=True, default=str))
        elif isinstance(val, UUID):
            parts.append(str(val))
        else:
            try:
                hash(val)
                parts.append(str(val))
            except TypeError:
                parts.append(json.dumps(val, sort_keys=True, default=str))
    return tuple(parts)


# ---------------------------------------------------------------------------
# Session-singleton caches (built once from the persistent, shared test DB)
# ---------------------------------------------------------------------------

_tables_cache: Optional[List[str]] = None
_dirty_tables_cache: Optional[List[str]] = None
_empty_tables_cache: Optional[List[str]] = None
_fk_graph_cache: Optional[Dict[str, List[str]]] = None
_delete_order_cache: Optional[List[str]] = None
_baseline_cache: Optional[Dict[str, Dict[str, Any]]] = None
_baseline_lock = threading.Lock()


def _all_tables(engine) -> List[str]:
    global _tables_cache
    if _tables_cache is not None:
        return _tables_cache
    inspector = sa_inspect(engine)
    _tables_cache = [
        t
        for t in inspector.get_table_names()
        if not t.startswith("_") and t not in _TABLE_SKIP_NAMES
    ]
    return _tables_cache


def _get_fk_graph(engine) -> Dict[str, List[str]]:
    global _fk_graph_cache
    if _fk_graph_cache is None:
        _fk_graph_cache = build_fk_graph(engine)
    return _fk_graph_cache


def _get_delete_order(engine) -> List[str]:
    global _delete_order_cache
    if _delete_order_cache is None:
        _delete_order_cache = topological_delete_order(_get_fk_graph(engine))
    return _delete_order_cache


def _classify_tables(session, engine) -> Tuple[List[str], List[str]]:
    """Return (tables_with_rows, tables_empty). Computed once per session.

    Uses a batched UNION count so the one-time classification cost is a
    single round trip rather than N round trips.
    """
    global _dirty_tables_cache, _empty_tables_cache
    if _dirty_tables_cache is not None and _empty_tables_cache is not None:
        return _dirty_tables_cache, _empty_tables_cache

    tables = _all_tables(engine)
    parts = []
    params = {}
    for i, t in enumerate(tables):
        pn = f"pn{i}"
        parts.append(f"(SELECT :{pn} AS name, count(*) AS cnt FROM \"{t}\")")
        params[pn] = t
    stmt = " UNION ALL ".join(parts)

    dirty, empty = [], []
    with engine.begin() as conn:
        rows = conn.execute(text(stmt), params).all()
    counts = {r[0]: r[1] for r in rows}
    for t in tables:
        if counts.get(t, 0) > 0:
            dirty.append(t)
        else:
            empty.append(t)

    _dirty_tables_cache = dirty
    _empty_tables_cache = empty
    return dirty, empty


def discover_dirty_tables(session, engine) -> List[str]:
    """Tables that had rows at session start (cached)."""
    dirty, _ = _classify_tables(session, engine)
    return dirty


def discover_all_tables(engine) -> List[str]:
    """Return every public table name in the schema (uncached, cheap)."""
    return _all_tables(engine)


def reset_dirty_tables_cache():
    """Reset the table-state caches (call after schema changes)."""
    global _tables_cache, _dirty_tables_cache, _empty_tables_cache
    global _fk_graph_cache, _delete_order_cache, _baseline_cache
    _tables_cache = None
    _dirty_tables_cache = None
    _empty_tables_cache = None
    _fk_graph_cache = None
    _delete_order_cache = None
    _baseline_cache = None


# ---------------------------------------------------------------------------
# Snapshot / cleanup API
# ---------------------------------------------------------------------------

def _build_baseline(session, engine) -> Dict[str, Dict[str, Any]]:
    """Capture the session-start row baseline for every table.

    Called lazily on the first test and reused for the whole session.
    """
    dirty, empty = _classify_tables(session, engine)
    snapshot: Dict[str, Dict[str, Any]] = {}
    read_conn = engine.connect()
    try:
        for table_name in dirty:
            try:
                snap = snapshot_table_rows_readonly(read_conn, table_name)
                snap["pre_count"] = snap["count"]
                snapshot[table_name] = snap
            except Exception:
                pass
        for table_name in empty:
            snapshot[table_name] = {"pre_count": 0, "pk_type": "none", "count": 0}
    finally:
        read_conn.close()
    return snapshot


def take_snapshot(session, engine) -> Dict[str, Dict[str, Any]]:
    """Return the session-start baseline snapshot of every table.

    The baseline is computed lazily ONCE (before the first test runs) and
    cached. Because cleanup restores each table to its session-start state
    after every test, the same baseline is correct for every per-test
    cleanup — no per-test reflection or row scan is needed.
    """
    global _baseline_cache
    if _baseline_cache is None:
        with _baseline_lock:
            if _baseline_cache is None:
                _baseline_cache = _build_baseline(session, engine)
    return _baseline_cache


def cleanup_inserted_rows(
    conn, engine, snapshot: Dict[str, Dict[str, Any]]
) -> Dict[str, int]:
    """Delete rows inserted during the test, in FK-safe order.

    Returns {table: rows_deleted}.
    """
    # The baseline snapshot covers every table (dirty + empty), so the
    # FK-safe delete order is the same for every cleanup — use the cached one.
    delete_order = _get_delete_order(engine)

    # Pass 1: revert FK mutations on pre-existing rows.
    for table_name in delete_order:
        snap = snapshot.get(table_name)
        if snap:
            revert_fk_mutations(conn, table_name, snap)

    # Pass 2: delete test-created rows in FK-safe order.
    deleted: Dict[str, int] = {}
    for table_name in delete_order:
        snap = snapshot[table_name]
        count = cleanup_table(conn, table_name, snap)
        if count > 0:
            deleted[table_name] = count
    return deleted