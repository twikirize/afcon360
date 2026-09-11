"""Isolation-contract tests for the test-isolation architecture.

Verifies the systemic guarantees that the conftest relies on:

- ``topological_delete_order`` returns dependents-first (FK-safe) ordering,
  so cleanup never triggers a RestrictViolation by deleting a parent row
  while a child row still references it.
- ``cleanup_inserted_rows`` restores every table to its session baseline
  (both dirty tables and empty tables), including rows connected via FKs.
- The autouse ``_isolate_config`` fixture restores ``app.config`` between
  tests (nested mutation restore).
- The autouse ``_clean_cache`` fixture clears the shared cache between tests.

These tests are deliberately cross-test: some assert that state written in a
preceding test does NOT leak into the following one.
"""

import uuid

import pytest

from app.extensions import db, cache
from app.identity.models.user import User
from app.identity.models.organisation import Organisation
from tests.helpers.isolation import (
    build_fk_graph,
    topological_delete_order,
    take_snapshot,
    cleanup_inserted_rows,
)


# =====================================================================
# 1. FK-safe delete ordering (pure graph property, no rows needed)
# =====================================================================

def test_delete_order_is_fk_safe(app):
    """Every table must be deleted AFTER all tables that reference it.

    If table A has an FK to table B, A is a dependent of B and must be
    deleted first. The delete-order test below asserts that for every FK
    dependency, the dependent precedes the parent in the delete order.
    """
    engine = db.engine
    graph = build_fk_graph(engine)
    order = topological_delete_order(graph)
    position = {table: idx for idx, table in enumerate(order)}

    assert len(order) == len(set(order)), "delete order contains duplicates"

    for table, referred in graph.items():
        for parent in referred:
            if parent == table:
                # Self-referential FK (e.g. users.emergency_access_granted_by
                # -> users). The topo sort deliberately skips self-edges;
                # a table's single position trivially satisfies it.
                continue
            assert position[table] < position[parent], (
                f"FK-SAFE ORDER VIOLATION: {table} (FK to {parent}) must be "
                f"deleted before {parent}; got positions "
                f"{position[table]} > {position[parent]}"
            )


# =====================================================================
# 2. Cleanup restores the session baseline (rows inserted via FK chain)
# =====================================================================

def test_cleanup_restores_baseline_with_fk_chain(app, unique_id):
    """Insert a User + Organisation (FK child) and confirm cleanup
    removes both, restoring the tables to their session baseline."""
    baseline = take_snapshot(db.session, db.engine)

    with app.app_context():
        suffix = unique_id
        user = User(
            username=f"iso-contract-{suffix}",
            email=f"iso-contract-{suffix}@test.example.com",
            is_verified=True,
            is_active=True,
        )
        user.set_password('TestPass123!')
        db.session.add(user)
        db.session.flush()

        org = Organisation(
            org_id=f"iso-{suffix}",
            country="UG",
            region="Central",
            legal_name=f"Isolation Contract {suffix}",
            org_type="business",
            referred_by=user.id,
        )
        db.session.add(org)
        db.session.commit()
        user_pid = str(user.public_id)

    # Guard: both rows are really visible before cleanup.
    with app.app_context():
        assert User.query.filter_by(public_id=user_pid).first() is not None
        assert Organisation.query.filter_by(org_id=f"iso-{suffix}").first() is not None

    # Run the same cleanup path the conftest uses (raw connection).
    with db.engine.begin() as conn:
        deleted = cleanup_inserted_rows(conn, db.engine, baseline)

    assert deleted.get("organisations", 0) >= 1, "organisation row not cleaned"
    assert deleted.get("users", 0) >= 1, "user row not cleaned"

    with app.app_context():
        assert User.query.filter_by(public_id=user_pid).first() is None
        assert Organisation.query.filter_by(org_id=f"iso-{suffix}").first() is None


def test_cleanup_deletes_rows_from_initially_empty_table(app, unique_id):
    """A row inserted into a table that started empty must be removed."""
    baseline = take_snapshot(db.session, db.engine)

    with app.app_context():
        user = User(
            username=f"iso-empty-{unique_id}",
            email=f"iso-empty-{unique_id}@test.example.com",
            is_verified=True,
            is_active=True,
        )
        user.set_password('TestPass123!')
        db.session.add(user)
        db.session.commit()
        user_pid = str(user.public_id)

    with db.engine.begin() as conn:
        deleted = cleanup_inserted_rows(conn, db.engine, baseline)

    assert deleted.get("users", 0) >= 1

    with app.app_context():
        assert User.query.filter_by(public_id=user_pid).first() is None


# =====================================================================
# 3. Config isolation — nested mutation restored between tests
# =====================================================================

_CROSS_TEST_MARKER_KEY = "ISOLATION_CONTRACT_MARKER"


def test_config_mutation_does_not_leak_prep(app):
    """This test runs FIRST: it mutates config. The next test asserts the
    mutation was restored."""
    assert _CROSS_TEST_MARKER_KEY not in app.config
    app.config[_CROSS_TEST_MARKER_KEY] = "leaked-if-seen"


def test_config_mutation_restored_between_tests(app):
    """Runs AFTER test_config_mutation_does_not_leak_prep; the autouse
    _isolate_config fixture must have reverted the mutation."""
    assert _CROSS_TEST_MARKER_KEY not in app.config, (
        "app.config mutation leaked across tests: _isolate_config failed to "
        "restore the baseline config."
    )


# =====================================================================
# 4. Cache isolation — cache written in one test cleared before the next
# =====================================================================

_CROSS_TEST_CACHE_KEY = "isolation_contract_cache_key"


def test_cache_write_does_not_leak_prep(app):
    """This test runs FIRST: it writes a shared-cache key."""
    with app.app_context():
        cache.set(_CROSS_TEST_CACHE_KEY, "leaked-if-seen")


def test_cache_cleared_between_tests(app):
    """Runs AFTER test_cache_write_does_not_leak_prep; the autouse
    _clean_cache fixture must have cleared the key."""
    with app.app_context():
        assert cache.get(_CROSS_TEST_CACHE_KEY) is None, (
            "cache value leaked across tests: _clean_cache failed to clear "
            "the shared cache before the next test."
        )