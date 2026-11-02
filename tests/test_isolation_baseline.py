"""Focused tests for safe, complete test-database baseline capture."""

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, insert, select

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

    def snapshot(_connection, table_name):
        if table_name == "cannot_snapshot":
            raise PermissionError("permission denied")
        return {"count": 1, "pk_type": "int"}

    monkeypatch.setattr(isolation, "snapshot_table_rows_readonly", snapshot)

    with pytest.raises(RuntimeError, match="cannot_snapshot") as exc_info:
        isolation._build_baseline(None, engine)

    assert isinstance(exc_info.value.__cause__, PermissionError)
    assert engine.connection.closed is True


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
