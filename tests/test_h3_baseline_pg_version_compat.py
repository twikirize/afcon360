"""Regression tests for PostgreSQL-version handling in the active H3-A baseline."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "h3a20261020_static_baseline.py"
)
SPEC = spec_from_file_location("_h3a20261020_baseline_under_test", MIGRATION_PATH)
assert SPEC is not None and SPEC.loader is not None
BASELINE = module_from_spec(SPEC)
SPEC.loader.exec_module(BASELINE)

TRANSACTION_TIMEOUT = "SET transaction_timeout = 0;\\n"


@pytest.mark.parametrize("server_version_num", [150000, 150014, 160000, 160009])
def test_pre_postgresql_17_omits_only_unsupported_setting(server_version_num):
    original_sql = BASELINE._SCHEMA_SQL
    assert original_sql.count(TRANSACTION_TIMEOUT) == 1

    compatible_sql = BASELINE._schema_sql_for_server_version(
        original_sql, server_version_num
    )

    assert compatible_sql == original_sql.replace(TRANSACTION_TIMEOUT, "", 1)
    assert "SET transaction_timeout = 0;" not in compatible_sql
    assert BASELINE._SCHEMA_SQL == original_sql


@pytest.mark.parametrize("server_version_num", [170000, 170006, 180000, 180004])
def test_postgresql_17_or_newer_preserves_original_sql(server_version_num):
    original_sql = BASELINE._SCHEMA_SQL

    assert BASELINE._schema_sql_for_server_version(
        original_sql, server_version_num
    ) == original_sql


def test_pre_17_fails_closed_if_expected_setting_is_missing_or_duplicated():
    with pytest.raises(RuntimeError, match="Expected exactly one transaction_timeout"):
        BASELINE._schema_sql_for_server_version("SELECT 1;\\n", 150000)

    with pytest.raises(RuntimeError, match="Expected exactly one transaction_timeout"):
        BASELINE._schema_sql_for_server_version(
            TRANSACTION_TIMEOUT + TRANSACTION_TIMEOUT, 150000
        )
