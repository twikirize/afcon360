"""Focused tests for safe, complete test-database baseline capture."""

import pytest
from sqlalchemy import (
    Column,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    insert,
    select,
)

from tests.helpers import isolation


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


def test_integer_fk_restore_includes_zero_primary_key():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    parent = Table(
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
    metadata.create_all(engine)

    try:
        with engine.begin() as connection:
            connection.execute(insert(parent), [{"id": 11}, {"id": 22}])
            connection.execute(
                insert(child), {"id": 0, "parent_id": 11}
            )

        with engine.connect() as connection:
            baseline = isolation.snapshot_table_rows_readonly(
                connection, "isolation_fk_child_probe"
            )
        assert baseline["max_pk"] == 0
        assert baseline["int_pks"] == {0}

        with engine.begin() as connection:
            connection.execute(
                child.update().where(child.c.id == 0).values(parent_id=22)
            )

        with engine.begin() as connection:
            reverted = isolation.revert_fk_mutations(
                connection, "isolation_fk_child_probe", baseline
            )

        assert reverted == 1
        with engine.connect() as connection:
            parent_id = connection.execute(
                select(child.c.parent_id).where(child.c.id == 0)
            ).scalar_one()
        assert parent_id == 11
    finally:
        engine.dispose()


def test_integer_primary_key_cleanup_removes_new_ids_inside_existing_gap():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    table = Table(
        "isolation_int_pk_gap_probe",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("label", String(40), nullable=False),
    )
    metadata.create_all(engine)

    try:
        with engine.begin() as connection:
            connection.execute(
                insert(table),
                [{"id": 10, "label": "baseline-low"}, {"id": 20, "label": "baseline-high"}],
            )

        with engine.connect() as connection:
            baseline = isolation.snapshot_table_rows_readonly(
                connection, "isolation_int_pk_gap_probe"
            )

        assert baseline["max_pk"] == 20
        assert baseline["int_pks"] == {10, 20}

        # A manually assigned PK can land inside the pre-existing ID range.
        with engine.begin() as connection:
            connection.execute(
                insert(table),
                {"id": 15, "label": "test-created-gap-row"},
            )

        with engine.begin() as connection:
            deleted = isolation.cleanup_table(
                connection, "isolation_int_pk_gap_probe", baseline
            )

        assert deleted == 1
        with engine.connect() as connection:
            remaining = set(
                connection.execute(select(table.c.id)).scalars().all()
            )
        assert remaining == {10, 20}
    finally:
        engine.dispose()
