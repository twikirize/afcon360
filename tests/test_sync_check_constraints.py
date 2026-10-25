"""Contract tests for scripts/sync_check_constraints.py (Stage 2).

Two properties are under test, and they pull in opposite directions:

  1. DISCOVERY MUST BE COMPLETE. The inventory has to contain every CHECK
     constraint the database declares, whatever it is called. Filtering the
     inventory by name prefix produced the historical false-zero result:
     ``transport_bookings.chk_pickup_time_future`` existed in the database,
     was invisible to the tool, and the report confidently said
     "0 orphaned constraints".

  2. RECONCILIATION MUST STAY NARROW. A wider inventory must not become a
     wider blast radius. Only managed ``ck_`` rows may become ADD / REPLACE
     / prune operations; legacy ``chk_`` rows are reported, never migrated,
     unless the human names them explicitly with ``--drop-legacy``.

``normalize_sql`` is tested for BOTH directions: pairs that are genuinely
the same predicate must compare equal (otherwise a destructive DROP+RECREATE
is proposed for an unchanged constraint), and pairs that differ in meaning
must stay different (otherwise a real difference is silently accepted).
"""

import importlib.util
import pathlib
import sys

import pytest


# ---------------------------------------------------------------------------
# Module under test
# ---------------------------------------------------------------------------

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "sync_check_constraints.py"


def _load_sync_module():
    """Import the synchronizer as a module without running ``main()``."""

    spec = importlib.util.spec_from_file_location(
        "afcon360_sync_check_constraints", _SCRIPT
    )
    assert spec and spec.loader

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sync = _load_sync_module()

normalize_sql = sync.normalize_sql
classify_constraint = sync.classify_constraint
partition_checks = sync.partition_checks
count_by_prefix = sync.count_by_prefix
diff = sync.diff
build_migration = sync.build_migration


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

class TestClassifyConstraint:
    """``ck_`` managed, ``chk_`` legacy, anything else unknown-but-legacy."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("ck_pickup_time_sane", "managed"),
            ("ck_notifications_type", "managed"),
            ("ck_", "managed"),
            ("chk_pickup_time_future", "legacy"),
            ("chk_vehicle_year", "legacy"),
            ("cardinal_number_domain_check", "other"),
            ("yes_or_no_check", "other"),
            ("ck", "other"),
        ],
    )
    def test_classification(self, name, expected):
        assert classify_constraint(name) == expected

    def test_managed_is_never_legacy(self):
        assert classify_constraint("ck_x") != "legacy"

    def test_legacy_prefix_is_a_tuple_not_a_single_string(self):
        # A bare string would make startswith('chk_') match character by
        # character in other call sites; assert the configured shape.
        assert isinstance(sync.LEGACY_PREFIXES, tuple)
        assert "chk_" in sync.LEGACY_PREFIXES


class TestPartitionChecks:

    def test_splits_by_name_not_by_presence(self):
        checks = {
            ("t", "ck_a"): "a > 0",
            ("t", "chk_b"): "b > 0",
            ("t", "yes_or_no_check"): "c > 0",
            ("t", "ck_c"): "c > 0",
        }

        managed, legacy = partition_checks(checks)

        assert set(managed) == {("t", "ck_a"), ("t", "ck_c")}
        assert set(legacy) == {("t", "chk_b"), ("t", "yes_or_no_check")}

    def test_is_total_no_row_is_dropped(self):
        checks = {
            ("t", "ck_a"): "x",
            ("t", "chk_b"): "y",
            ("t", "zz_other"): "z",
        }

        managed, legacy = partition_checks(checks)

        assert len(managed) + len(legacy) == len(checks)

    def test_count_by_prefix_matches_partition(self):
        checks = {
            ("t", "ck_a"): "x",
            ("t", "ck_b"): "y",
            ("t", "chk_c"): "z",
            ("t", "other_d"): "w",
        }

        counts = count_by_prefix(checks)
        managed, legacy = partition_checks(checks)

        assert counts == {"ck_": 2, "chk_": 1, "other": 1}
        assert len(managed) == 2
        assert len(legacy) == 2


# ---------------------------------------------------------------------------
# normalize_sql -- pairs that must compare EQUAL
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "db_sql,model_sql,reason",
    [
        (
            "CHECK ((pickup_time > (created_at - '00:05:00'::interval)))",
            "pickup_time > created_at - INTERVAL '5 minutes'",
            "same 300s window, two spellings",
        ),
        (
            "CHECK ((ts > (now() - '300 seconds'::interval)))",
            "ts > now() - INTERVAL '5 minutes'",
            "seconds spelling",
        ),
        (
            "CHECK ((ts > (now() - '00:00:30'::interval)))",
            "ts > now() - INTERVAL '30 seconds'",
            "mm:ss spelling",
        ),
        (
            "CHECK (((year >= 2000) AND "
            "((year)::numeric <= "
            "(EXTRACT(year FROM CURRENT_DATE) + (1)::numeric))))",
            "year >= 2000 AND year <= EXTRACT(YEAR FROM CURRENT_DATE) + 1",
            "redundant arithmetic parens",
        ),
        (
            "CHECK ((a <= (b + c)))",
            "a <= b + c",
            "paren is right operand of a comparison",
        ),
        (
            "CHECK (((a + b) <= c))",
            "a + b <= c",
            "paren is left operand of a comparison",
        ),
        (
            "CHECK ((channel)::text = ANY (ARRAY["
            "('in_app'::character varying)::text, "
            "('email'::character varying)::text]))",
            "channel IN ('in_app', 'email')",
            "reflection ANY/ARRAY vs model IN",
        ),
        (
            "CHECK ((status = 'active'))",
            "CHECK (status = 'active')",
            "outer CHECK wrapper",
        ),
        (
            "  pickup_time > created_at  ",
            "pickup_time > created_at",
            "whitespace only",
        ),
    ],
)
def test_normalize_equal_pairs(db_sql, model_sql, reason):
    assert normalize_sql(db_sql) == normalize_sql(model_sql), reason


# ---------------------------------------------------------------------------
# normalize_sql -- pairs that must stay DIFFERENT
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "left,right,reason",
    [
        (
            "CHECK ((a - (b - c) > 0))",
            "CHECK ((a - b - c > 0))",
            "a-(b-c) != a-b-c",
        ),
        (
            "CHECK ((a / (b * c) > 0))",
            "CHECK ((a / b * c > 0))",
            "a/(b*c) != a/b*c",
        ),
        (
            "CHECK ((ts > (now() - '1 mon'::interval)))",
            "CHECK ((ts > (now() - INTERVAL '30 days')))",
            "one month is not thirty days",
        ),
        (
            "CHECK ((status = 'active'))",
            "CHECK ((status = 'inactive'))",
            "different literal",
        ),
        (
            "CHECK ((a > 1))",
            "CHECK ((b > 1))",
            "different column",
        ),
        (
            "CHECK ((a > 1))",
            "CHECK ((a >= 1))",
            "different operator",
        ),
        (
            "CHECK ((a >= 1 AND b > 2 OR c > 3))",
            "CHECK (((a >= 1 OR b > 2) AND c > 3))",
            "different boolean grouping",
        ),
        (
            "CHECK ((a - interval(300) > 0))",
            "CHECK ((a - interval(600) > 0))",
            "different interval magnitude",
        ),
    ],
)
def test_normalize_keeps_different_pairs_apart(left, right, reason):
    assert normalize_sql(left) != normalize_sql(right), reason


class TestIntervalToken:
    """Fixed durations collapse; calendar units and unknowns never do."""

    @pytest.mark.parametrize(
        "literal,expected",
        [
            ("00:05:00", "interval(300)"),
            ("5 minutes", "interval(300)"),
            ("300 seconds", "interval(300)"),
            ("5 min", "interval(300)"),
            ("01:00:00", "interval(3600)"),
        ],
    )
    def test_fixed_durations_collapse(self, literal, expected):
        assert sync._interval_token(literal) == expected

    @pytest.mark.parametrize(
        "literal",
        ["1 month", "1 mon", "2 months"],
    )
    def test_calendar_units_keep_a_calendar_suffix(self, literal):
        assert "mon)" in sync._interval_token(literal)

    @pytest.mark.parametrize(
        "literal", ["2 years", "1 year"]
    )
    def test_years_are_not_days(self, literal):
        token = sync._interval_token(literal)
        assert "yr)" in token
        assert "86400" not in token

    def test_month_never_becomes_a_day_count(self):
        assert sync._interval_token("1 month") != sync._interval_token(
            "30 days"
        )

    def test_unknown_unit_keeps_its_value_distinct(self):
        assert sync._interval_token("3 bananas") != sync._interval_token(
            "4 bananas"
        )

    def test_unparseable_literal_never_collapses_to_a_shared_token(self):
        a = sync._interval_token("banana")
        b = sync._interval_token("durian")
        assert a != b
        assert "banana" in a


class TestArithParenCanonicalization:

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("a <= (b + c)", "a <= b + c"),
            ("(a + b) <= c", "a + b <= c"),
            ("(a - b) - c", "a - b - c"),
            ("a <= ((extract(y from d)) + 1)",
             "a <= extract(y from d) + 1"),
        ],
    )
    def test_removes_redundant_grouping(self, text, expected):
        assert sync._canonicalize_arith(text) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "a - (b - c)",
            "a * (b + c)",
            "a / (b * c)",
            "a % (b + c)",
        ],
    )
    def test_preserves_meaning_changing_grouping(self, text):
        assert sync._canonicalize_arith(text) == text

    def test_function_call_parens_are_not_grouping(self):
        assert sync._canonicalize_arith("interval(300) = x") == (
            "interval(300) = x"
        )

    def test_in_list_is_left_alone(self):
        assert sync._canonicalize_arith("x in (1, 2)") == "x in (1, 2)"

    def test_descends_into_non_redundant_outer_group(self):
        # The outer group carries boolean structure (not redundant), but
        # the inner arithmetic group is redundant. Skipping the outer
        # group wholesale would hide the drift this pass exists to find.
        result = sync._canonicalize_arith(
            "((year) <= (extract(y from d) + (1)))"
        )
        assert "(year)" not in result
        assert "(extract(y from d) + (1))" not in result


# ---------------------------------------------------------------------------
# diff -- discovery completeness and reconciliation narrowness
# ---------------------------------------------------------------------------

def _build_diff(model, db):
    return diff(
        {(t, n): sql for (t, n), sql in model.items()},
        {(t, n): sql for (t, n), sql in db.items()},
    )


class TestDiffDiscoveryIsComplete:
    """A prefix filter in the inventory would produce a false zero here."""

    def test_legacy_db_only_row_is_reported_not_hidden(self):
        # Regression: this exact row existed in the database and was
        # invisible to the tool, which then printed "0 orphaned".
        result = _build_diff(
            model={
                ("transport_bookings", "ck_pickup_time_sane"):
                    "pickup_time > created_at - INTERVAL '5 minutes'",
            },
            db={
                ("transport_bookings", "ck_pickup_time_sane"):
                    "pickup_time > created_at - INTERVAL '5 minutes'",
                ("transport_bookings", "chk_pickup_time_future"):
                    "pickup_time > created_at",
            },
        )

        assert [key for key, _ in result.to_drop_legacy] == [
            ("transport_bookings", "chk_pickup_time_future")
        ]

    def test_legacy_db_only_row_never_becomes_a_prune_candidate(self):
        result = _build_diff(
            model={},
            db={("t", "chk_orphan"): "a > 0"},
        )

        assert result.to_drop_managed == []
        assert len(result.to_drop_legacy) == 1

    def test_legacy_missing_from_db_is_not_an_add(self):
        result = _build_diff(
            model={("t", "chk_gone"): "a > 0"},
            db={},
        )

        assert result.to_add == []
        assert result.to_drop_legacy == []

    def test_unknown_prefix_rows_are_inventoried(self):
        result = _build_diff(
            model={},
            db={("t", "yes_or_no_check"): "flag in ('y','n')"},
        )

        assert [key for key, _ in result.to_drop_legacy] == [
            ("t", "yes_or_no_check")
        ]


class TestDiffReconciliationIsManagedOnly:

    def test_managed_missing_from_db_is_added(self):
        result = _build_diff(
            model={("t", "ck_new"): "a > 0"},
            db={},
        )

        assert [key for key, _ in result.to_add] == [("t", "ck_new")]

    def test_legacy_drift_is_reported_but_not_replaced(self):
        result = _build_diff(
            model={("t", "chk_x"): "a > 0"},
            db={("t", "chk_x"): "a > 1"},
        )

        assert result.to_replace == []
        assert [key for key, _, _ in result.to_replace_legacy] == [
            ("t", "chk_x")
        ]

    def test_managed_drift_becomes_a_replace(self):
        result = _build_diff(
            model={("t", "ck_x"): "a > 0"},
            db={("t", "ck_x"): "a > 1"},
        )

        assert [key for key, _, _ in result.to_replace] == [("t", "ck_x")]

    def test_equivalent_but_differently_written_is_representation_only(self):
        result = _build_diff(
            model={("t", "ck_x"): "pickup_time > created_at - INTERVAL '5 minutes'"},
            db={("t", "ck_x"): "pickup_time > (created_at - '00:05:00'::interval)"},
        )

        assert result.to_replace == []
        assert [key for key, _, _ in result.representation_matches] == [
            ("t", "ck_x")
        ]

    def test_no_op_when_everything_matches(self):
        checks = {("t", "ck_a"): "a > 0", ("t", "chk_b"): "b > 0"}
        result = _build_diff(model=checks, db=checks)

        assert result.to_add == []
        assert result.to_replace == []
        assert result.to_drop_managed == []
        assert result.to_drop_legacy == []
        assert result.to_replace_legacy == []
        assert not result.has_managed_drift


class TestDiffConflicts:

    def test_legacy_row_overlapping_a_managed_constraint_is_flagged(self):
        # The real case: chk_pickup_time_future constrains the same
        # columns as ck_pickup_time_sane on the same table.
        result = _build_diff(
            model={
                ("transport_bookings", "ck_pickup_time_sane"):
                    "pickup_time > created_at - INTERVAL '5 minutes'",
            },
            db={
                ("transport_bookings", "ck_pickup_time_sane"):
                    "pickup_time > created_at - INTERVAL '5 minutes'",
                ("transport_bookings", "chk_pickup_time_future"):
                    "pickup_time > created_at",
            },
        )

        assert [key for key, _, _ in result.conflicts] == [
            ("transport_bookings", "chk_pickup_time_future")
        ]
        table, name = result.conflicts[0][0]
        assert table == "transport_bookings"
        assert name == "chk_pickup_time_future"
        assert ("transport_bookings", "ck_pickup_time_sane") in (
            result.conflicts[0][2]
        )

    def test_legacy_row_on_unrelated_columns_is_not_a_conflict(self):
        result = _build_diff(
            model={("t", "ck_alpha"): "alpha_id > 0"},
            db={
                ("t", "ck_alpha"): "alpha_id > 0",
                ("t", "chk_beta"): "beta_id > 0",
            },
        )

        assert result.conflicts == []

    def test_conflicts_are_reported_even_when_nothing_is_migratable(self):
        result = _build_diff(
            model={},
            db={("t", "chk_lonely"): "alpha_id > 0"},
        )

        # No conflict on its own (no managed model constraint), and
        # certainly no managed drift -- but the legacy row is still seen.
        assert result.to_add == []
        assert result.to_replace == []
        assert [key for key, _ in result.to_drop_legacy] == [
            ("t", "chk_lonely")
        ]


# ---------------------------------------------------------------------------
# build_migration -- the last line of defence
# ---------------------------------------------------------------------------

class TestBuildMigrationContract:

    def _kwargs(self):
        return {
            "down_revision": "abc123",
            "environment": "development",
            "message": "test",
        }

    def test_refuses_to_add_a_legacy_named_constraint(self):
        with pytest.raises(ValueError, match="non-managed"):
            build_migration(
                to_add=[(("t", "chk_new"), "a > 0")],
                to_drop=[],
                to_replace=[],
                **self._kwargs(),
            )

    def test_refuses_to_replace_a_legacy_named_constraint(self):
        with pytest.raises(ValueError, match="non-managed"):
            build_migration(
                to_add=[],
                to_drop=[],
                to_replace=[(("t", "chk_x"), "a > 0", "a > 1")],
                **self._kwargs(),
            )

    def test_accepts_managed_add_and_replace(self):
        content = build_migration(
            to_add=[(("t", "ck_new"), "a > 0")],
            to_drop=[],
            to_replace=[(("t", "ck_x"), "a > 0", "a > 1")],
            **self._kwargs(),
        )

        assert content is not None
        assert "ck_new" in content
        assert "chk_" not in content

    def test_returns_none_when_there_is_nothing_to_do(self):
        content = build_migration(
            to_add=[],
            to_drop=[],
            to_replace=[],
            **self._kwargs(),
        )

        assert content is None

    def test_an_authorised_legacy_drop_is_emitted(self):
        # Allowed only because the caller (main()) already checked
        # --prune-db + --drop-legacy before handing this row over.
        content = build_migration(
            to_add=[],
            to_drop=[(("transport_bookings", "chk_pickup_time_future"),
                      "pickup_time > created_at")],
            to_replace=[],
            **self._kwargs(),
        )

        assert content is not None
        assert "chk_pickup_time_future" in content
        assert "drop_constraint" in content

    def test_downgrade_restores_a_dropped_constraint(self):
        content = build_migration(
            to_add=[],
            to_drop=[(("t", "ck_x"), "a > 0")],
            to_replace=[],
            **self._kwargs(),
        )

        assert content is not None
        upgrade, downgrade = content.split("def downgrade():")
        assert "drop_constraint" in upgrade
        assert "create_check_constraint" in downgrade
        assert "'a > 0'" in downgrade


# ---------------------------------------------------------------------------
# Live-database read-only cross-check (optional)
# ---------------------------------------------------------------------------

def test_db_inventory_is_prefix_agnostic():
    """Read-only cross-check against pg_constraint.

    Skipped when PostgreSQL is unavailable. Asserts the two facts the
    original tool got wrong: legacy ``chk_`` rows are present in the
    inventory, and the managed/legacy split is computed from the DB
    itself rather than from a name filter applied before reading.
    """

    pytest.importorskip("sqlalchemy")

    try:
        from app import create_app
        from app.extensions import db
        from sqlalchemy import text
        app = create_app()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"application unavailable: {exc}")

    with app.app_context():
        engine = db.engine

        db_checks = sync.get_db_checks(engine)

        rows = engine.connect().execute(
            text(
                "SELECT conrelid::regclass::text, conname "
                "FROM pg_constraint "
                "WHERE contype = 'c' AND conrelid <> 0"
            )
        ).fetchall()

    expected = {(row[0], row[1]) for row in rows}

    assert set(db_checks) == expected, (
        "inventory must contain every TABLE CHECK constraint, "
        "whatever its prefix"
    )

    # Domain CHECK constraints (conrelid = 0) live in pg_constraint but
    # are not table constraints; get_table_names() correctly skips them.
    with app.app_context():
        domain_checks = engine.connect().execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE contype = 'c' AND conrelid = 0"
            )
        ).fetchall()

    domain_names = {row[0] for row in domain_checks}
    inventory_names = {name for _, name in db_checks}

    assert domain_names.isdisjoint(inventory_names), (
        "domain constraints must not appear in the table inventory"
    )

    managed, legacy = partition_checks(db_checks)

    assert set(managed) | set(legacy) == expected
    assert set(managed) & set(legacy) == set()

    db_legacy_names = {key[1] for key in legacy}
    assert all(
        not name.startswith("ck_") for name in db_legacy_names
    ), "partition must not leak managed names into the legacy bucket"
