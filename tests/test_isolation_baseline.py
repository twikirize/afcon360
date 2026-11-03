"""Focused tests for safe, complete test-database baseline capture."""

import pytest
from sqlalchemy import Column, ForeignKeyConstraint, Integer, MetaData, Table

from tests.helpers import isolation


pytestmark = pytest.mark.no_database


def test_baseline_capture_fails_closed_with_table_specific_error(monkeypatch):
    class Connection:
        closed = False

        def close(self):
            self.closed = True

    class Engine:
        def __init__(self):
            self.connection = Connection()

        def connect(self):
            return self.connection

    engine = Engine()
    monkeypatch.setattr(
        isolation,
        "_classify_tables",
        lambda _session, _engine: (["already_populated", "cannot_snapshot"], ["empty_table"]),
    )
    monkeypatch.setattr(
        isolation,
        "_get_delete_order",
        lambda _engine: ["already_populated", "cannot_snapshot", "empty_table"],
    )

    def snapshot(_connection, table_name):
        if table_name == "cannot_snapshot":
            raise PermissionError("permission denied")
        return {"count": 1, "pk_type": "int"}

    monkeypatch.setattr(isolation, "snapshot_table_rows_readonly", snapshot)

    with pytest.raises(RuntimeError, match="cannot_snapshot") as exc_info:
        isolation._build_baseline(None, engine)

    assert isinstance(exc_info.value.__cause__, PermissionError)
    assert engine.connection.closed is True


def test_fk_metadata_failure_stops_baseline_before_tests(monkeypatch):
    class Inspector:
        default_schema_name = "public"

        def get_table_names(self):
            return ["cannot_inspect_fk_metadata"]

        def get_foreign_keys(self, table_name):
            raise PermissionError(f"no FK metadata access for {table_name}")

    monkeypatch.setattr(isolation, "sa_inspect", lambda _engine: Inspector())
    monkeypatch.setattr(
        isolation,
        "_classify_tables",
        lambda _session, _engine: (["cannot_inspect_fk_metadata"], []),
    )
    monkeypatch.setattr(isolation, "_fk_graph_cache", None)
    monkeypatch.setattr(isolation, "_delete_order_cache", None)

    with pytest.raises(RuntimeError, match="cannot_inspect_fk_metadata") as exc_info:
        isolation._build_baseline(None, object())

    assert isinstance(exc_info.value.__cause__, PermissionError)


def test_delete_order_rejects_unresolvable_fk_cycles(monkeypatch):
    monkeypatch.setattr(
        isolation,
        "_get_fk_graph",
        lambda _engine: {"child": ["parent"], "parent": ["child"]},
    )
    monkeypatch.setattr(isolation, "_delete_order_cache", None)

    with pytest.raises(RuntimeError, match="not acyclic"):
        isolation._get_delete_order(object())


def test_isolation_timings_are_opt_in(monkeypatch, capsys):
    monkeypatch.delenv("TEST_ISOLATION_TIMINGS", raising=False)
    isolation._emit_isolation_timing("probe", elapsed=0.25)
    assert capsys.readouterr().out == ""

    monkeypatch.setenv("TEST_ISOLATION_TIMINGS", "1")
    isolation._emit_isolation_timing("probe", elapsed=0.25, tables=12)
    captured = capsys.readouterr().out
    assert "[TEST_ISOLATION_TIMING] probe" in captured
    assert "elapsed=0.2500s" in captured
    assert "tables=12" in captured


def _table_with_fk():
    metadata = MetaData()
    Table(
        "isolation_fk_parent_probe",
        metadata,
        Column("id", Integer, primary_key=True),
    )
    child = Table(
        "isolation_fk_child_probe",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("parent_id", Integer, nullable=False),
        ForeignKeyConstraint(
            ["parent_id"], ["isolation_fk_parent_probe.id"]
        ),
    )
    return child


class _FakeResult:
    def __init__(self, rows=(), rowcount=None):
        self._rows = list(rows)
        self.rowcount = rowcount

    def __iter__(self):
        return iter(self._rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


def test_integer_fk_restore_includes_zero_primary_key(monkeypatch):
    table = _table_with_fk()

    class Connection:
        def __init__(self):
            self.statements = []

        def execute(self, statement):
            self.statements.append(statement)
            if len(self.statements) == 1:
                # The pre-existing row with PK zero has been mutated by the test.
                return _FakeResult(rows=[(0, 22)])
            return _FakeResult(rowcount=1)

    connection = Connection()
    monkeypatch.setattr(
        isolation, "_reflect_table", lambda _bind, _name: table
    )

    baseline = {
        "pk_type": "int",
        "pk_columns": ["id"],
        "int_pks": {0},
        "fk_columns": ["parent_id"],
        "fk_baseline": {0: {"parent_id": 11}},
    }

    reverted = isolation.revert_fk_mutations(
        connection, "isolation_fk_child_probe", baseline
    )

    assert reverted == 1
    assert len(connection.statements) == 2
    selected_params = connection.statements[0].compile().params
    assert any(value == 0 or value == [0] for value in selected_params.values())
    update_values = connection.statements[1].compile().params
    assert 0 in update_values.values()
    assert 11 in update_values.values()


def test_integer_primary_key_cleanup_removes_new_ids_inside_existing_gap(monkeypatch):
    metadata = MetaData()
    table = Table(
        "isolation_int_pk_gap_probe",
        metadata,
        Column("id", Integer, primary_key=True),
    )

    class Session:
        def __init__(self):
            self.statements = []

        def get_bind(self):
            return object()

        def execute(self, statement):
            self.statements.append(statement)
            if len(self.statements) == 1:
                # ID 15 was added inside the baseline's existing 0..20 range.
                return _FakeResult(rows=[0, 10, 15, 20])
            return _FakeResult(rowcount=1)

    session = Session()
    monkeypatch.setattr(
        isolation, "_reflect_table", lambda _bind, _name: table
    )

    deleted = isolation.cleanup_table(
        session,
        "isolation_int_pk_gap_probe",
        {"pk_type": "int", "pk_columns": ["id"], "int_pks": {0, 10, 20}},
    )

    assert deleted == 1
    assert len(session.statements) == 2
    delete_params = session.statements[1].compile().params
    assert any(value == 15 or value == [15] for value in delete_params.values())
