"""Regression tests for binary-safe OCI backup restore input handling."""

from __future__ import annotations

import gzip
import subprocess
from types import SimpleNamespace

import pytest

from scripts.ops import restore_oci_backup_to_test_db as restore


pytestmark = pytest.mark.no_database


def test_gzip_restore_stream_is_decompressed_and_passed_to_psql_as_bytes(
    tmp_path, monkeypatch
):
    # Deliberately include a byte that is not valid UTF-8. The restore utility
    # must not decode SQL dump bytes in Python before handing them to psql.
    sql_bytes = b"-- binary-safe restore test\nSELECT 1;\n-- raw byte: \xfa\n"
    backup_path = tmp_path / "database_manual_test.sql.gz"
    with gzip.open(backup_path, "wb") as compressed:
        compressed.write(sql_bytes)

    monkeypatch.setattr(restore.shutil, "which", lambda _: "/usr/bin/psql")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if kwargs.get("stdin") is not None:
            assert kwargs["text"] is False
            assert kwargs["stdin"].read() == sql_bytes
            return subprocess.CompletedProcess(command, 0, b"", b"")

        sql = command[-1]
        if "alembic_version" in sql:
            return subprocess.CompletedProcess(
                command, 0, b"afcon360_restore_test_case|rev_test|1|1|1\n", b""
            )
        return subprocess.CompletedProcess(
            command, 0, b"afcon360_restore_test_case|0\n", b""
        )

    monkeypatch.setattr(restore.subprocess, "run", fake_run)

    config = {
        "database": "afcon360_restore_test_case",
        "pg_host": "127.0.0.1",
        "pg_port": "5433",
        "pg_user": "restore_test_user",
        "pg_password": "disposable-test-password",
    }
    result = restore._restore_to_test_database(
        config,
        backup_path,
        timeout=30,
        expected_revision="rev_test",
        expected_table_count=1,
        expected_users_count=1,
        expected_marker="OCI_TEST_MARKER",
    )

    assert result == {
        "table_count": 1,
        "alembic_revision": "rev_test",
        "users_count": 1,
        "marker_count": 1,
    }
    assert len(calls) == 3
    restored_sql_path = backup_path.with_suffix("")
    assert restored_sql_path.read_bytes() == sql_bytes
    assert restored_sql_path.stat().st_mode & 0o777 == 0o600


def test_restore_input_uses_plain_sql_file_without_copying(tmp_path):
    sql_path = tmp_path / "database_manual_test.sql"
    sql_path.write_bytes(b"SELECT 1;\n")

    assert restore._prepare_restore_input(sql_path) == sql_path


def test_corrupt_gzip_restore_input_leaves_no_partial_sql_file(tmp_path):
    backup_path = tmp_path / "database_manual_test.sql.gz"
    backup_path.write_bytes(b"not a valid gzip archive")

    with pytest.raises((OSError, EOFError)):
        restore._prepare_restore_input(backup_path)

    assert not backup_path.with_suffix("").exists()
