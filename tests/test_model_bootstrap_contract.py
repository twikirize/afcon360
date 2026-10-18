"""Focused contract tests for the Design-2 model-bootstrap path.

Every test here is marked ``no_database``: they assert source behaviour and
model-metadata invariants and never create, alter or query database rows.
"""

from pathlib import Path

import pytest
from sqlalchemy import (
    Column,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    MetaData,
    Table,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum

from app.core.model_bootstrap import (
    GROUP_A_EXPECTED,
    GROUP_B_EXPECTED,
    MARKER_KEY,
    MARKER_TABLE,
    STATE_CONTRADICTORY,
    STATE_EMPTY,
    STATE_MIGRATION_BUILT_AT_HEAD,
    STATE_MIGRATION_BUILT_NOT_AT_HEAD,
    STATE_MODEL_BOOTSTRAP_BUILDING,
    STATE_MODEL_BOOTSTRAP_COMPLETE,
    STATE_UNMARKED_NONEMPTY,
    DatabaseState,
    MarkerRow,
    ModelBootstrapError,
    SchemaProbe,
    assert_inventory_ownership,
    bootstrap_model_schema,
    build_enum_type_block,
    classify_database_state,
    collect_enum_specs,
    compute_schema_fingerprint,
    labels_identical,
    partition_enum_ownership,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


class FakeProbe(SchemaProbe):
    """In-memory SchemaProbe so classification needs no database."""

    def __init__(self, tables=(), marker=None, revisions=()):
        self._tables = list(tables)
        self._marker = marker
        self._revisions = tuple(revisions)

    def table_names(self):
        return list(self._tables)

    def marker_row(self):
        return self._marker

    def alembic_revisions(self):
        return self._revisions


@pytest.fixture(scope="module")
def model_metadata():
    """The real application metadata, built without touching a database."""
    from app import create_app
    from app.core.model_registry import register_all_models
    from app.extensions import db

    register_all_models()
    app = create_app()
    with app.app_context():
        yield db.metadata


def _metadata_with(enums):
    metadata = MetaData()
    Table(
        "sample",
        metadata,
        Column("id", Integer, primary_key=True),
        *[Column(f"col_{index}", enum) for index, enum in enumerate(enums)],
    )
    return metadata


# --------------------------------------------------------------------------
# Enum ownership and the reviewed inventory
# --------------------------------------------------------------------------


@pytest.mark.no_database
def test_model_metadata_matches_the_reviewed_47_type_inventory(model_metadata):
    """The models and the reviewed Addendum B inventory must agree exactly."""
    group_a, group_b = partition_enum_ownership(collect_enum_specs(model_metadata))

    assert len(group_a) == 39, sorted(group_a)
    assert len(group_b) == 8, sorted(group_b)
    assert len(group_a) + len(group_b) == 47
    assert_inventory_ownership(group_a, group_b)


@pytest.mark.no_database
def test_group_a_and_group_b_are_disjoint(model_metadata):
    group_a, group_b = partition_enum_ownership(collect_enum_specs(model_metadata))
    assert not (set(group_a) & set(group_b))


@pytest.mark.no_database
def test_create_type_false_is_the_only_signal_for_group_a():
    """Group membership is decided by create_type, not by name or location."""
    metadata = _metadata_with(
        [
            PGEnum("X", "Y", name="owned_by_bootstrap", create_type=False),
            PGEnum("X", "Y", name="owned_by_create_all", create_type=True),
            PGEnum("X", "Y", name="owned_by_create_all_implicit"),
        ]
    )
    group_a, group_b = partition_enum_ownership(collect_enum_specs(metadata))

    assert set(group_a) == {"owned_by_bootstrap"}
    assert set(group_b) == {"owned_by_create_all", "owned_by_create_all_implicit"}


@pytest.mark.no_database
def test_conflicting_definitions_of_one_type_are_rejected():
    """One type name may have exactly one definition and one owner."""
    metadata = _metadata_with(
        [
            SAEnum("X", "Y", name="clashing", create_type=False),
            SAEnum("X", "Z", name="clashing", create_type=False),
        ]
    )
    with pytest.raises(ModelBootstrapError, match="conflicting"):
        collect_enum_specs(metadata)


@pytest.mark.no_database
def test_inventory_drift_is_rejected():
    """A model change cannot silently change enum ownership."""
    with pytest.raises(ModelBootstrapError, match="no longer declared"):
        assert_inventory_ownership(
            {name: labels for name, labels in GROUP_A_EXPECTED.items() if name != "currency"},
            GROUP_B_EXPECTED,
        )


@pytest.mark.no_database
def test_inventory_label_order_change_is_rejected():
    reordered = dict(GROUP_A_EXPECTED)
    reordered["currency"] = tuple(reversed(GROUP_A_EXPECTED["currency"]))
    with pytest.raises(ModelBootstrapError, match="label order changed"):
        assert_inventory_ownership(reordered, GROUP_B_EXPECTED)


@pytest.mark.no_database
def test_labels_identical_is_exact_and_order_sensitive():
    assert labels_identical(["A", "B"], ["A", "B"])
    assert not labels_identical(["A", "B"], ["B", "A"])
    assert not labels_identical(["A", "B"], ["a", "b"])
    assert not labels_identical(["A"], ["A", "B"])


# --------------------------------------------------------------------------
# CREATE TYPE block
# --------------------------------------------------------------------------


@pytest.mark.no_database
def test_enum_block_never_uses_if_not_exists():
    """PostgreSQL has no CREATE TYPE IF NOT EXISTS; the block must not pretend."""
    block = build_enum_type_block("transactiontype", ("DEPOSIT", "WITHDRAWAL"))
    assert "IF NOT EXISTS" not in block
    assert "CREATE TYPE transactiontype AS ENUM (" in block


@pytest.mark.no_database
def test_enum_block_is_schema_scoped_and_refuses_an_incompatible_type():
    block = build_enum_type_block("transactiontype", ("DEPOSIT", "WITHDRAWAL"))
    assert block.count("current_schema()") >= 3
    assert "IS DISTINCT FROM" in block
    assert "RAISE EXCEPTION" in block
    assert "refusing to reuse or rewrite it" in block


@pytest.mark.no_database
def test_enum_block_preserves_label_order_and_case():
    block = build_enum_type_block("gender_enum", ("male", "female", "other"))
    assert block.index("male") < block.index("female") < block.index("other")


@pytest.mark.no_database
def test_enum_block_rejects_an_unsafe_type_name():
    with pytest.raises(ModelBootstrapError, match="unsafe identifier"):
        build_enum_type_block("drop table users; --", ("A",))


@pytest.mark.no_database
def test_enum_block_quotes_labels_defensively():
    block = build_enum_type_block("quoted_enum", ("it's", "ok"))
    assert "'it''s'" in block


@pytest.mark.no_database
def test_enum_block_retains_raise_exception_placeholders():
    """The generated block must keep % placeholders for RAISE EXCEPTION."""
    block = build_enum_type_block("transactiontype", ("DEPOSIT", "WITHDRAWAL"))
    # The RAISE EXCEPTION uses % placeholders that must survive to execution
    assert "RAISE EXCEPTION" in block
    assert "'AFCON360 enum type % already exists in schema % with incompatible labels" in block
    # Ensure we have exactly 2 % placeholders (type name, schema name)
    # Count % that are not part of %% (escaped)
    import re
    # Find % not followed by % and not preceded by %
    placeholders = re.findall(r'(?<!%)%(?!%)', block)
    assert len(placeholders) == 2, f"Expected 2 % placeholders, found {len(placeholders)}: {placeholders}"


@pytest.mark.no_database
def test_ensure_group_a_types_uses_no_parameters(monkeypatch):
    """_ensure_group_a_types must pass execution_options=no_parameters."""
    import app.core.model_bootstrap as mb
    from unittest.mock import MagicMock

    captured = {}

    def fake_exec_driver_sql(sql, execution_options=None):
        captured["sql"] = sql
        captured["execution_options"] = execution_options
        return None

    conn = MagicMock()
    conn.exec_driver_sql = fake_exec_driver_sql

    mb._ensure_group_a_types(conn, {"test_enum": ("A", "B")})

    assert captured.get("execution_options") == {"no_parameters": True}
    assert "RAISE EXCEPTION" in captured.get("sql", "")


# --------------------------------------------------------------------------
# Schema-scope consistency (read_persisted_enum_labels vs build_enum_type_block)
# --------------------------------------------------------------------------


@pytest.mark.no_database
def test_read_persisted_enum_labels_uses_current_schema():
    """read_persisted_enum_labels must query current_schema(), not hardcoded public."""
    import app.core.model_bootstrap as mb
    import sqlalchemy as sa

    # The query should use current_schema() function
    source = Path(mb.__file__).read_text(encoding="utf-8")
    assert "current_schema()" in source
    # Verify the WHERE clause uses current_schema()
    assert "_PG_NAMESPACE.c.nspname == sa.func.current_schema()" in source


@pytest.mark.no_database
def test_schema_scope_contract_consistent_in_source():
    """read_persisted_enum_labels and build_enum_type_block use the same active schema."""
    # Source-level contract: both the query and the DO block reference current_schema().
    import app.core.model_bootstrap as mb
    source = Path(mb.__file__).read_text(encoding="utf-8")
    # The query filters by current_schema()
    assert "_PG_NAMESPACE.c.nspname == sa.func.current_schema()" in source
    # build_enum_type_block also uses current_schema() in its DO block
    block = mb.build_enum_type_block("test_iso", ("X", "Y"))
    assert block.count("current_schema()") >= 3
    # Both use the same active schema, ensuring consistency


# --------------------------------------------------------------------------
# Classification of database states
# --------------------------------------------------------------------------


@pytest.mark.no_database
def test_classify_empty_database():
    state = classify_database_state(FakeProbe(tables=()), heads=("head",))
    assert state.code == STATE_EMPTY


@pytest.mark.no_database
def test_classify_complete_model_bootstrap():
    probe = FakeProbe(
        tables=[MARKER_TABLE, "users"],
        marker=MarkerRow(MARKER_KEY, "complete", "abc123"),
    )
    state = classify_database_state(probe, heads=("head",))
    assert state.code == STATE_MODEL_BOOTSTRAP_COMPLETE
    assert state.marker_fingerprint == "abc123"
    assert state.is_model_bootstrap


@pytest.mark.no_database
def test_classify_interrupted_model_bootstrap_is_not_success():
    probe = FakeProbe(
        tables=[MARKER_TABLE, "users"],
        marker=MarkerRow(MARKER_KEY, "building", "abc123"),
    )
    state = classify_database_state(probe, heads=("head",))
    assert state.code == STATE_MODEL_BOOTSTRAP_BUILDING
    assert "did not complete" in state.describe()


@pytest.mark.no_database
def test_classify_migration_built_at_head():
    probe = FakeProbe(tables=["alembic_version", "users"], revisions=("head",))
    state = classify_database_state(probe, heads=("head",))
    assert state.code == STATE_MIGRATION_BUILT_AT_HEAD
    assert state.revision == "head"


@pytest.mark.no_database
def test_classify_migration_built_not_at_head():
    probe = FakeProbe(tables=["alembic_version"], revisions=("older",))
    state = classify_database_state(probe, heads=("head",))
    assert state.code == STATE_MIGRATION_BUILT_NOT_AT_HEAD


@pytest.mark.no_database
def test_classify_unmarked_nonempty_database_is_refused():
    probe = FakeProbe(tables=["users", "events"])
    state = classify_database_state(probe, heads=("head",))
    assert state.code == STATE_UNMARKED_NONEMPTY
    assert "neither the model-bootstrap marker nor alembic_version" in state.describe()


@pytest.mark.no_database
def test_classify_contradictory_database():
    probe = FakeProbe(
        tables=[MARKER_TABLE, "alembic_version", "users"],
        marker=MarkerRow(MARKER_KEY, "complete", "abc123"),
        revisions=("head",),
    )
    state = classify_database_state(probe, heads=("head",))
    assert state.code == STATE_CONTRADICTORY


@pytest.mark.no_database
def test_marker_table_is_not_a_model_table(model_metadata):
    """The marker must never be confusable with the application schema."""
    assert MARKER_TABLE not in model_metadata.tables
    assert MARKER_TABLE != "alembic_version"


# --------------------------------------------------------------------------
# Registration failures block bootstrap before any database access
# --------------------------------------------------------------------------


@pytest.mark.no_database
def test_model_registration_has_no_failures():
    from app.core.model_registry import registration_failures

    assert registration_failures() == {}


@pytest.mark.no_database
def test_bootstrap_refuses_an_incomplete_model_set(monkeypatch):
    """Registration is checked before metadata or the engine is touched."""
    import app.core.model_registry as registry

    monkeypatch.setattr(
        registry,
        "registration_failures",
        lambda: {"events": "ImportError: boom"},
    )

    class _ExplodingDb:
        @property
        def metadata(self):
            raise AssertionError("metadata must not be read")

        @property
        def engine(self):
            raise AssertionError("engine must not be touched")

    with pytest.raises(ModelBootstrapError, match="incomplete model set"):
        bootstrap_model_schema(_ExplodingDb(), ("head",))


@pytest.mark.no_database
def test_bootstrap_refuses_real_import_failure(monkeypatch):
    """A real import failure in the registry is recorded and blocks bootstrap."""
    import app.core.model_registry as registry

    # Force a real import failure by patching one of the lazy imports
    original_import = __import__

    def failing_import(name, *args, **kwargs):
        if name == "app.accommodation.models":
            raise ImportError("Simulated accommodation models import failure")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(
        "builtins.__import__",
        failing_import,
    )

    # Clear any previous failures via monkeypatch to avoid mutating global state
    monkeypatch.setattr(registry, "_REGISTRATION_FAILURES", {})

    # This will trigger the import failure and record it
    registry.register_all_models()

    # Verify the failure was recorded
    failures = registry.registration_failures()
    assert "accommodation" in failures
    assert "ImportError" in failures["accommodation"]
    assert "Simulated accommodation models import failure" in failures["accommodation"]

    # Now verify bootstrap refuses before any database access
    class _ExplodingDb:
        @property
        def metadata(self):
            raise AssertionError("metadata must not be read")

        @property
        def engine(self):
            raise AssertionError("engine must not be touched")

    with pytest.raises(ModelBootstrapError, match="incomplete model set"):
        bootstrap_model_schema(_ExplodingDb(), ("head",))


# --------------------------------------------------------------------------
# Fingerprinting
# --------------------------------------------------------------------------


@pytest.mark.no_database
def test_fingerprint_is_deterministic(model_metadata):
    assert compute_schema_fingerprint(model_metadata) == compute_schema_fingerprint(
        model_metadata
    )


@pytest.mark.no_database
def test_fingerprint_changes_when_a_column_changes():
    before = compute_schema_fingerprint(
        _metadata_with([SAEnum("A", name="fp_enum")])
    )
    after = compute_schema_fingerprint(
        _metadata_with([SAEnum("A", "B", name="fp_enum")])
    )
    assert before != after


@pytest.mark.no_database
def test_fingerprint_ignores_constraint_object_identity():
    """Unnamed constraints live in a set; the digest must not depend on identity.

    Regression: ordering constraints by ``name`` leaves ties for the many
    unnamed constraints, so the digest followed set iteration order and
    differed between processes. That would make repeat-invocation validation
    report a spurious mismatch.
    """

    def build():
        metadata = MetaData()
        Table("parent", metadata, Column("id", Integer, primary_key=True))
        Table(
            "child",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("parent_id", Integer, ForeignKey("parent.id")),
        )
        return metadata

    assert compute_schema_fingerprint(build()) == compute_schema_fingerprint(build())


# --------------------------------------------------------------------------
# No false Alembic head stamp anywhere
# --------------------------------------------------------------------------


FALSE_STAMP_MARKERS = (
    "alembic_stamp",
    "flask_migrate import stamp",
    '"db", "stamp"',
)


@pytest.mark.no_database
@pytest.mark.parametrize(
    "relative_path",
    [
        "tests/conftest.py",
        "scripts/setup_test_db_schema.py",
        "scripts/setup_test_db.py",
        "tests/browser/start_test_server.py",
    ],
)
def test_no_false_alembic_head_stamp_in_provisioning_paths(relative_path):
    """Nothing that builds a schema from models may stamp Alembic head."""
    source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
    for marker in FALSE_STAMP_MARKERS:
        assert marker not in source, f"{relative_path} still references {marker!r}"


@pytest.mark.no_database
def test_conftest_no_longer_provisions_schema():
    """pytest must not create schema; the operator provisions it."""
    source = (PROJECT_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "db.create_all" not in source
    assert "classify_database_state" in source


@pytest.mark.no_database
def test_migration_equivalence_rejects_a_marked_database():
    source = (
        PROJECT_ROOT / "tests" / "postgres_contract.py"
    ).read_text(encoding="utf-8")
    assert "MARKER_TABLE" in source
    assert "model-bootstrap path" in source


@pytest.mark.no_database
def test_bootstrap_module_never_writes_alembic_version():
    """alembic_version is only read and rejected; never written or stamped."""
    source = (
        PROJECT_ROOT / "app" / "core" / "model_bootstrap.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "alembic_stamp",
        "flask_migrate",
        "ALEMBIC_VERSION_TABLE.insert",
        "ALEMBIC_VERSION_TABLE.update",
        "ALEMBIC_VERSION_TABLE.delete",
    ):
        assert forbidden not in source
    assert '"alembic_version"' in source


@pytest.mark.no_database
def test_database_state_codes_are_distinct():
    codes = {
        STATE_EMPTY,
        STATE_MODEL_BOOTSTRAP_BUILDING,
        STATE_MODEL_BOOTSTRAP_COMPLETE,
        STATE_MIGRATION_BUILT_AT_HEAD,
        STATE_MIGRATION_BUILT_NOT_AT_HEAD,
        STATE_UNMARKED_NONEMPTY,
        STATE_CONTRADICTORY,
    }
    assert len(codes) == 7
    assert DatabaseState(code=STATE_EMPTY).is_empty
    assert not DatabaseState(code=STATE_MIGRATION_BUILT_AT_HEAD).is_model_bootstrap
