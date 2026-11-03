"""DB row-tracking isolation for test lifecycle.

Tracks rows inserted during each test and cleans them up at teardown,
eliminating cross-test pollution from committed data.

Design:
- The test DB is shared and persists across RUNS. Cleanup restores every
  table to its session-start state after each test, so the schema's
  "dirty" (has rows) / "empty" classification is stable for the session.
  Because of that, a single baseline captured ONCE per session is valid for
  every per-test cleanup:
    - int PK tables   -> exact session-start set of ids (plus max for diagnostics)
    - UUID PK tables  -> session-start set of ids
    - other/composite -> session-start canonical row set
    - empty tables    -> "was empty" marker (cleanup = DELETE ALL rows,
                         since any row found there is test-created)
- Cleanup DELETE:
    - int table       -> DELETE rows whose id is not in baseline set
    - uuid table      -> DELETE rows whose id is not in baseline set
    - other tables    -> DELETE each current row not in baseline set
    - empty table     -> DELETE ALL
  FK-safe delete order is computed once from a cached FK graph.
- Baseline is lazily computed on the first test (before ANY test inserts),
  so fixture-created rows (test_user, test_admin, ...) are captured as
  post-baseline and cleaned up like any other test data.

PK strategies (per table):
  - integer PK     -> exact pre-existing ID set (max retained for diagnostics)
  - UUID PK        -> exact pre-existing ID set
  - composite PK   -> full-row snapshot (row equality)
  - no PK          -> full-row snapshot (row equality)

This is the "Option B — Row tracking + explicit cleanup" architecture.
"""

import json
import os
import threading
import time
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy import (
    JSON, MetaData, Table, Text, and_, cast, delete, func, literal,
    select, union_all, update, inspect as sa_inspect,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.auth.deletion_guard import authorize_deletion


def _isolation_timings_enabled() -> bool:
    return os.getenv("TEST_ISOLATION_TIMINGS", "").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _emit_isolation_timing(phase: str, **measurements: Any) -> None:
    """Emit opt-in phase diagnostics; normal test output stays quiet."""
    if not _isolation_timings_enabled():
        return
    parts = []
    for name, value in measurements.items():
        if isinstance(value, float):
            parts.append(f"{name}={value:.4f}s")
        else:
            parts.append(f"{name}={value}")
    print(
        "[TEST_ISOLATION_TIMING] "
        + phase
        + (" " + " ".join(parts) if parts else ""),
        flush=True,
    )


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
        except Exception as exc:
            raise RuntimeError(
                "Test isolation cannot inspect foreign keys for table "
                f"{table_name!r}; refusing to build an incomplete delete graph."
            ) from exc
        for fk in fks:
            parent = fk.get("referred_table")
            if not parent:
                raise RuntimeError(
                    "Test isolation received incomplete foreign-key metadata "
                    f"for table {table_name!r}: referred_table is missing."
                )
            if parent not in table_names:
                referred_schema = fk.get("referred_schema")
                if referred_schema in (None, inspector.default_schema_name):
                    raise RuntimeError(
                        "Test isolation foreign-key metadata for table "
                        f"{table_name!r} refers to missing table {parent!r}."
                    )
                # External-schema parents are not among the tables cleaned here.
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
    except Exception as exc:
        raise RuntimeError(
            "Test isolation cannot inspect foreign-key columns for table "
            f"{table_name!r}."
        ) from exc
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
    except Exception as exc:
        raise RuntimeError(
            "Test isolation cannot inspect primary-key metadata for table "
            f"{table_name!r}."
        ) from exc


# Reflected table metadata is schema-stable for the lifetime of a pytest worker.
# The isolation teardown touches every table twice per test; reflecting each
# table on every pass was the dominant avoidable cost in the timed CI run.
_reflected_tables_cache: Dict[Tuple[int, str], Table] = {}
_reflected_engines: Dict[int, Any] = {}
_reflected_tables_lock = threading.RLock()


def _reflect_table(bind, table_name: str) -> Table:
    """Return cached metadata for one table on the current bound Engine."""
    get_bind = getattr(bind, "get_bind", None)
    resolved_bind = get_bind() if callable(get_bind) else bind
    engine = getattr(resolved_bind, "engine", resolved_bind)
    if engine is None:
        raise RuntimeError(
            f"Test isolation cannot resolve an Engine to reflect table {table_name!r}."
        )

    engine_key = id(engine)
    cache_key = (engine_key, table_name)
    with _reflected_tables_lock:
        table = _reflected_tables_cache.get(cache_key)
        if table is None:
            table = Table(table_name, MetaData(), autoload_with=engine)
            _reflected_tables_cache[cache_key] = table
            # Retain the Engine so its identity cannot be recycled while its
            # cached Table objects remain addressable.
            _reflected_engines[engine_key] = engine
        return table


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
            # Explicit/manual PK inserts can fill gaps below max(id). Preserve
            # the exact baseline IDs so teardown never misses those rows.
            snap["int_pks"] = set(values)
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
        baseline_ids = snap.get("int_pks")
        if baseline_ids is not None:
            if not baseline_ids:
                return 0
            statement = statement.where(pk_column.in_(list(baseline_ids)))
        else:
            # Compatibility with baselines created before exact integer IDs
            # were stored. Include zero-valued IDs rather than assuming a
            # positive sequence boundary.
            max_pk = snap.get("max_pk")
            if max_pk is None:
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
        pk_column = table.c[snap["pk_columns"][0]]
        baseline_ids = snap.get("int_pks")
        if baseline_ids is None:
            # Compatibility for a baseline captured by older helper code.
            max_pk = snap.get("max_pk", 0)
            statement = delete(table)
            if max_pk != 0:
                statement = statement.where(pk_column > max_pk)
            return session.execute(statement).rowcount or 0

        current_values = session.execute(select(pk_column)).scalars().all()
        to_delete = [value for value in current_values if value not in baseline_ids]
        deleted = 0
        for index in range(0, len(to_delete), 1000):
            batch = to_delete[index:index + 1000]
            if batch:
                result = session.execute(delete(table).where(pk_column.in_(batch)))
                deleted += result.rowcount or 0
        return deleted

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
        graph = _get_fk_graph(engine)
        order = topological_delete_order(graph)
        position = {table_name: index for index, table_name in enumerate(order)}
        missing = set(graph) - set(position)
        unexpected = set(position) - set(graph)
        if missing or unexpected:
            raise RuntimeError(
                "Test isolation delete-order coverage mismatch: "
                f"missing={sorted(missing)!r}, unexpected={sorted(unexpected)!r}"
            )
        for table_name, parents in graph.items():
            for parent in parents:
                if parent == table_name:
                    continue
                if position[table_name] >= position[parent]:
                    raise RuntimeError(
                        "Test isolation FK dependency graph is not acyclic or "
                        "does not produce a safe delete order: "
                        f"{table_name!r} must be deleted before {parent!r}."
                    )
        _delete_order_cache = order
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
    missing_counts = set(tables) - set(counts)
    unexpected_counts = set(counts) - set(tables)
    if missing_counts or unexpected_counts:
        raise RuntimeError(
            "Test isolation table classification was incomplete: "
            f"missing={sorted(missing_counts)!r}, "
            f"unexpected={sorted(unexpected_counts)!r}"
        )
    _dirty_tables_cache = [name for name in tables if counts[name] > 0]
    _empty_tables_cache = [name for name in tables if counts[name] == 0]
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
    with _reflected_tables_lock:
        _reflected_tables_cache.clear()
        _reflected_engines.clear()


# ---------------------------------------------------------------------------
# Snapshot / cleanup API
# ---------------------------------------------------------------------------

def _build_baseline(session, engine) -> Dict[str, Dict[str, Any]]:
    """Capture the session-start row baseline for every table.

    Called lazily on the first test and reused for the whole session.
    """
    total_started = time.perf_counter()
    classify_started = time.perf_counter()
    dirty, empty = _classify_tables(session, engine)
    classify_seconds = time.perf_counter() - classify_started
    expected_tables = set(dirty) | set(empty)

    # Validate the complete FK graph and safe delete order before the first
    # test executes. A partial graph can silently skip cleanup dependencies.
    order_started = time.perf_counter()
    delete_order = _get_delete_order(engine)
    order_seconds = time.perf_counter() - order_started
    order_tables = set(delete_order)
    missing_order = expected_tables - order_tables
    unexpected_order = order_tables - expected_tables
    if missing_order or unexpected_order:
        raise RuntimeError(
            "Test isolation FK graph does not cover the baseline schema: "
            f"missing={sorted(missing_order)!r}, "
            f"unexpected={sorted(unexpected_order)!r}"
        )

    snapshot: Dict[str, Dict[str, Any]] = {}
    snapshot_started = time.perf_counter()
    read_conn = engine.connect()
    try:
        for table_name in dirty:
            try:
                snap = snapshot_table_rows_readonly(read_conn, table_name)
                snap["pre_count"] = snap["count"]
                snapshot[table_name] = snap
            except Exception as exc:
                _emit_isolation_timing(
                    "baseline_capture_failed",
                    table=table_name,
                    elapsed=time.perf_counter() - total_started,
                )
                raise RuntimeError(
                    "Test isolation baseline capture failed for table "
                    f"{table_name!r}; stopping before tests run because teardown "
                    "cannot safely clean a partial baseline."
                ) from exc
        for table_name in empty:
            snapshot[table_name] = {"pre_count": 0, "pk_type": "none", "count": 0}
    finally:
        read_conn.close()

    snapshot_seconds = time.perf_counter() - snapshot_started
    missing = expected_tables - set(snapshot)
    unexpected = set(snapshot) - expected_tables
    if missing or unexpected:
        raise RuntimeError(
            "Test isolation baseline table coverage mismatch: "
            f"missing={sorted(missing)!r}, unexpected={sorted(unexpected)!r}"
        )
    _emit_isolation_timing(
        "baseline_capture",
        classify=classify_seconds,
        fk_graph=order_seconds,
        snapshot=snapshot_seconds,
        total=time.perf_counter() - total_started,
        populated_tables=len(dirty),
        empty_tables=len(empty),
    )
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
    total_started = time.perf_counter()
    authorize_started = time.perf_counter()
    # The migration-built test schema installs BEFORE DELETE guards. Reuse the
    # sanctioned SET LOCAL authorization so it cannot leak to pooled sessions.
    authorize_deletion(conn, actor="test-isolation-cleanup")
    authorize_seconds = time.perf_counter() - authorize_started

    order_started = time.perf_counter()
    delete_order = _get_delete_order(engine)
    order_seconds = time.perf_counter() - order_started
    missing_baseline = [name for name in delete_order if name not in snapshot]
    unexpected_baseline = set(snapshot) - set(delete_order)
    if missing_baseline or unexpected_baseline:
        raise RuntimeError(
            "Test isolation baseline/delete-order coverage mismatch: "
            f"missing_baseline={sorted(missing_baseline)!r}, "
            f"unexpected_baseline={sorted(unexpected_baseline)!r}"
        )

    # Pass 1: restore FK mutations on pre-existing rows.
    fk_started = time.perf_counter()
    fk_values_reverted = 0
    fk_table_timings = []
    for table_name in delete_order:
        snap = snapshot[table_name]
        table_started = time.perf_counter()
        fk_values_reverted += revert_fk_mutations(conn, table_name, snap)
        fk_table_timings.append((time.perf_counter() - table_started, table_name))
    fk_seconds = time.perf_counter() - fk_started

    # Pass 2: remove test-created rows in FK-safe order.
    row_cleanup_started = time.perf_counter()
    deleted: Dict[str, int] = {}
    cleanup_table_timings = []
    for table_name in delete_order:
        table_started = time.perf_counter()
        count = cleanup_table(conn, table_name, snapshot[table_name])
        elapsed = time.perf_counter() - table_started
        cleanup_table_timings.append((elapsed, table_name, count))
        if count > 0:
            deleted[table_name] = count
    row_cleanup_seconds = time.perf_counter() - row_cleanup_started

    slow_fk_tables = ";".join(
        f"{name}:{seconds:.3f}s"
        for seconds, name in sorted(fk_table_timings, reverse=True)[:5]
    )
    slow_cleanup_tables = ";".join(
        f"{name}:{seconds:.3f}s({count})"
        for seconds, name, count in sorted(cleanup_table_timings, reverse=True)[:8]
    )
    _emit_isolation_timing(
        "per_test_cleanup",
        authorize=authorize_seconds,
        delete_order=order_seconds,
        fk_restore=fk_seconds,
        row_cleanup=row_cleanup_seconds,
        total=time.perf_counter() - total_started,
        tables=len(delete_order),
        fk_values_reverted=fk_values_reverted,
        rows_deleted=sum(deleted.values()),
        touched_tables=len(deleted),
        slow_fk_tables=slow_fk_tables or "none",
        slow_cleanup_tables=slow_cleanup_tables or "none",
    )
    return deleted
