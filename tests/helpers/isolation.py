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

from sqlalchemy import (
    JSON, MetaData, Table, Text, and_, cast, delete, func, literal,
    select, union_all, update, inspect as sa_inspect,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.auth.deletion_guard import authorize_deletion


# ---------------------------------------------------------------------------
# Topological sort for FK-safe delete ordering
# ---------------------------------------------------------------------------

def build_fk_graph(engine) -> Dict[str, List[str]]:
    """Build a foreign-key dependency graph for all public tables.

    Returns {table: [referred_tables]} — i.e. which tables this table
    depends on via FK.

    Include NO ACTION / RESTRICT edges because they block parent deletion.
    Also include CASCADE edges: although they do not block a direct parent
    DELETE, deleting a parent may cascade through an intermediate child
    table which is itself referenced by a restrictive FK. Omitting that
    edge can make cleanup delete the grandparent too early (for example,
    organisations -> accommodation_properties -> accommodation_bookings).

    SET NULL / SET DEFAULT edges are excluded because parent deletion keeps
    the child row and only changes its FK value. Deferrable, initially
    deferred constraints are excluded because cleanup deletes test-created
    rows in one transaction.

    The known mutual-FK cycles in this schema are dissolved by SET NULL or
    deferred constraints; CASCADE edges needed for multi-hop delete ordering
    must remain in the graph.
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
            if ondelete in ("SET NULL", "SET DEFAULT"):
                continue  # child survives parent deletion; no delete-order edge
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
    """Return every FK column so baseline-row mutations can be restored.

    The snapshot is used to undo test changes to pre-existing rows before
    deleting test-created parents. Restoration is required for every
    ON DELETE action: CASCADE could otherwise delete a pre-existing child,
    while SET NULL / SET DEFAULT could silently alter its original value.
    """
    try:
        fks = inspector.get_foreign_keys(table_name)
    except Exception:
        return []
    cols: List[str] = []
    for fk in fks:
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


def _reflect_table(bind, table_name: str) -> Table:
    """Reflect one schema-verified table for SQLAlchemy Core operations."""
    return Table(table_name, MetaData(), autoload_with=bind)


def snapshot_table_rows_readonly(conn, table_name: str) -> Dict[str, Any]:
    """Snapshot a table using a dedicated Connection and SQLAlchemy Core."""
    inspector = sa_inspect(conn.engine)
    table = _reflect_table(conn, table_name)
    columns = list(table.c.keys())
    pk_cols = _get_pk_columns(inspector, table_name)
    fk_cols = _get_fk_columns(inspector, table_name)
    all_rows = [tuple(row) for row in conn.execute(select(table))]

    snap: Dict[str, Any] = {"columns": columns, "pk_columns": pk_cols, "count": len(all_rows)}
    if not pk_cols or len(pk_cols) > 2:
        snap["pk_type"] = "composite" if len(pk_cols) > 2 else "none"
        if all_rows:
            snap["row_snap"] = all_rows
        return snap

    if len(pk_cols) == 1:
        pk_col = pk_cols[0]
        pk_idx = columns.index(pk_col) if pk_col in columns else None
        if pk_idx is None:
            snap["pk_type"] = "none"
            if all_rows:
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
            isinstance(sample, str) and len(sample) == 36 or isinstance(sample, UUID)
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
            if all_rows:
                snap["row_snap"] = all_rows
        return snap

    snap["pk_type"] = "composite"
    if all_rows:
        snap["row_snap"] = all_rows
    return snap


# ---------------------------------------------------------------------------
# Cleanup logic
# ---------------------------------------------------------------------------

def revert_fk_mutations(conn, table_name: str, snap: Dict[str, Any]) -> int:
    """Restore FK values on pre-existing rows before deleting test-created rows."""
    fk_baseline = snap.get("fk_baseline") or {}
    fk_columns = snap.get("fk_columns") or []
    pk_cols = snap.get("pk_columns") or []
    if not fk_baseline or not fk_columns or len(pk_cols) != 1:
        return 0

    table = _reflect_table(conn, table_name)
    pk_column = table.c[pk_cols[0]]
    statement = select(pk_column, *(table.c[name] for name in fk_columns))
    pk_type = snap.get("pk_type")
    if pk_type == "int":
        max_pk = snap.get("max_pk", 0)
        if max_pk == 0:
            return 0
        statement = statement.where(pk_column <= max_pk)
    elif pk_type == "uuid":
        uuid_pks = list(snap.get("uuid_pks") or set())
        if not uuid_pks:
            return 0
        statement = statement.where(pk_column.in_(uuid_pks))
    else:
        return 0

    reverted = 0
    for row in conn.execute(statement):
        pk_val = row[0]
        key = str(pk_val) if isinstance(pk_val, UUID) else pk_val
        baseline = fk_baseline.get(key)
        if baseline is None:
            continue
        for index, column_name in enumerate(fk_columns, start=1):
            baseline_value = baseline.get(column_name)
            if row[index] != baseline_value:
                conn.execute(
                    update(table).where(pk_column == pk_val).values({column_name: baseline_value})
                )
                reverted += 1
    return reverted


def cleanup_table(session, table_name: str, snap: Dict[str, Any]) -> int:
    """Delete only rows inserted during the test using reflected Core tables."""
    bind = session.get_bind() if callable(getattr(session, "get_bind", None)) else session
    table = _reflect_table(bind, table_name)
    pk_type = snap.get("pk_type", "none")

    if pk_type == "int":
        max_pk = snap.get("max_pk", 0)
        statement = delete(table)
        if max_pk != 0:
            statement = statement.where(table.c[snap["pk_columns"][0]] > max_pk)
        return session.execute(statement).rowcount or 0

    if pk_type == "uuid":
        existing = snap.get("uuid_pks", set())
        pk_column = table.c[snap["pk_columns"][0]]
        if not existing:
            return session.execute(delete(table)).rowcount or 0
        current_values = session.execute(select(pk_column)).scalars().all()
        current_by_normalized = {
            str(value) if isinstance(value, UUID) else value: value
            for value in current_values
        }
        to_delete = [
            raw_value for normalized, raw_value in current_by_normalized.items()
            if normalized not in existing
        ]
        deleted = 0
        for index in range(0, len(to_delete), 1000):
            batch = to_delete[index:index + 1000]
            if batch:
                result = session.execute(delete(table).where(pk_column.in_(batch)))
                deleted += result.rowcount or 0
        return deleted

    if pk_type in ("none", "composite", "other"):
        row_snap = snap.get("row_snap", [])
        if not row_snap:
            return session.execute(delete(table)).rowcount or 0
        existing_set = {_canonical_row(row) for row in row_snap}
        current_rows = [tuple(row) for row in session.execute(select(table))]
        to_delete = [row for row in current_rows if _canonical_row(row) not in existing_set]
        deleted = 0
        for row in to_delete:
            predicates = []
            for column, value in zip(table.columns, row):
                if value is None:
                    predicates.append(column.is_(None))
                elif isinstance(column.type, (JSON, JSONB)):
                    predicates.append(
                        cast(column, Text) == cast(literal(value, type_=column.type), Text)
                    )
                else:
                    predicates.append(column == value)
            result = session.execute(delete(table).where(and_(*predicates)))
            deleted += result.rowcount or 0
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
    """Return session-start populated/empty tables in one Core UNION query."""
    global _dirty_tables_cache, _empty_tables_cache
    if _dirty_tables_cache is not None and _empty_tables_cache is not None:
        return _dirty_tables_cache, _empty_tables_cache

    tables = _all_tables(engine)
    if not tables:
        _dirty_tables_cache, _empty_tables_cache = [], []
        return _dirty_tables_cache, _empty_tables_cache

    metadata = MetaData()
    statements = [
        select(literal(table_name).label("name"), func.count().label("cnt"))
        .select_from(Table(table_name, metadata, autoload_with=engine))
        for table_name in tables
    ]
    with engine.begin() as conn:
        rows = conn.execute(union_all(*statements)).all()

    counts = {row[0]: row[1] for row in rows}
    _dirty_tables_cache = [name for name in tables if counts.get(name, 0) > 0]
    _empty_tables_cache = [name for name in tables if counts.get(name, 0) == 0]
    return _dirty_tables_cache, _empty_tables_cache


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
    # The migration-built test schema installs BEFORE DELETE guards
    # (trg_guard_users_delete, trg_guard_user_roles_delete) that raise
    # 42501 unless the transaction-scoped GUC app.guard.authorized_deletion
    # is 'true'. Reuse the sanctioned helper so the authorization is issued
    # as SET LOCAL: it ends with this cleanup transaction (commit/rollback)
    # and cannot leak to pooled sessions. Deletion targets are unchanged —
    # the snapshot logic below still removes exactly the rows identified as
    # test-created, never baseline data.
    authorize_deletion(conn, actor="test-isolation-cleanup")

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