"""Standalone source-only guards for timezone migration policy and lineage."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def source(path):
    return (ROOT / path).read_text(encoding="utf-8-sig")


def load_lineage_auditor():
    path = ROOT / "scripts" / "audit_timezone_migration_lineage.py"
    spec = spec_from_file_location("timezone_lineage_auditor", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_timezone_migration_requires_separate_explicit_column_classifications():
    migration = source(
        "migrations/versions/tza20261025_global_timezone_aware_timestamps.py"
    )
    assert "APPROVED_LEGACY_UTC_COLUMNS" in migration
    assert "APPROVED_LEGACY_WALL_CLOCK_COLUMNS" in migration
    assert "APPROVED_LEGACY_UTC_COLUMNS & APPROVED_LEGACY_WALL_CLOCK_COLUMNS" in migration
    assert "APPROVED_LEGACY_UTC_COLUMNS | APPROVED_LEGACY_WALL_CLOCK_COLUMNS" in migration
    assert "if key in APPROVED_LEGACY_WALL_CLOCK_COLUMNS:" in migration
    assert migration.count("= frozenset()") == 2
    assert "if discovered != approved_inventory:" in migration


def test_active_migration_graph_connects_current_draft_but_not_retired_db_revision():
    auditor = load_lineage_auditor()
    graph, issues = auditor.load_active_graph(ROOT)

    assert not issues, "\n".join(issues)
    assert graph["h3a20261020"]["parents"] == ()
    assert graph["c076b257b11d"]["parents"] == ("h3a20261020",)
    assert graph["1792869659"]["parents"] == ("c076b257b11d",)
    assert graph["tza20261025"]["parents"] == ("1792869659",)
    assert "df55cbe3f516" not in graph
    assert graph["h3a20261020"]["path"] == (
        "migrations/versions/h3a20261020_static_baseline.py"
    )


def test_timestamp_semantics_register_records_unresolved_database_gates():
    register = source("docs/architecture/TIMESTAMP_SEMANTICS_REGISTER.md")
    assert "no database columns are approved for conversion" in register
    assert "server_sessions.expires_at" in register
    assert "BookingRegistrationLink.expires_at" in register
    assert "The migration has **not** been run." in register
