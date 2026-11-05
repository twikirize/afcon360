"""Small-worker Celery configuration and scheduled-delivery contracts.

These tests are DB-free unless explicitly marked otherwise. They protect the
resource limits used by the 1 GiB production worker and verify that delivering
a scheduled Notification updates the existing row instead of duplicating it.
"""

import pytest

pytestmark = pytest.mark.no_database


def test_celery_worker_uses_single_prefetch_slot_and_recycles_children():
    from app.celery_app import celery_app

    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert celery_app.conf.worker_max_tasks_per_child == 50


def test_every_numeric_beat_tick_expires_before_its_next_interval():
    from app.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert schedule, "Celery Beat schedule must not be empty"

    for name, entry in schedule.items():
        interval = entry.get("schedule")
        if not isinstance(interval, (int, float)):
            continue

        expires = (entry.get("options") or {}).get("expires")
        assert expires is not None, f"{name} has no expiry"
        assert 0 < expires < interval, (
            f"{name} must expire stale queued ticks before the next interval"
        )

def test_expired_approval_hold_with_missing_legacy_sla_does_not_block_page(
    monkeypatch,
):
    """The stored expires_at is authoritative even for legacy NULL-SLA holds."""
    from datetime import datetime, timedelta, timezone

    from app import create_app
    from app.accommodation.models.availability import BlockedDate, RoomHold
    from app.accommodation.services.availability_service import AvailabilityService
    from app.extensions import db

    class _Query:
        def __init__(self, rows):
            self.rows = rows

        def filter(self, *criteria):
            return self

        def order_by(self, *criteria):
            return self

        def limit(self, amount):
            return self

        def all(self):
            return self.rows

    class _LegacyApprovalHold:
        id = 42
        status = "active"
        hold_type = "approval"
        approval_sla_hours = None
        expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

        def mark_expired(self):
            self.status = "expired"

    legacy_hold = _LegacyApprovalHold()
    app = create_app()
    with app.app_context():
        monkeypatch.setattr(BlockedDate, "query", _Query([]))
        monkeypatch.setattr(RoomHold, "query", _Query([legacy_hold]))
        monkeypatch.setattr(db.session, "commit", lambda: None)

        result = AvailabilityService.release_expired_holds(batch_size=25)

    assert legacy_hold.status == "expired"
    assert result["released"] == 1
    assert result["has_more"] is False

def test_transport_offer_expiry_sweep_uses_bounded_scan_cursors(monkeypatch):
    """The production sweep must not issue Redis KEYS or drain the keyspace at once."""
    from app.transport.services.offer_service import OfferService

    class _FakeRedis:
        def __init__(self):
            self.scans = []
            self.removed_members = []
            self.deleted_keys = []

        def scan(self, cursor, match, count):
            self.scans.append((cursor, match, count))
            if "transport:driver:" in match:
                return (0, [b"transport:driver:17:offers"]) if cursor == 0 else (0, [])
            return (
                (9, [b"transport:offer:index:booking:STALE"])
                if cursor == 0 else (0, [])
            )

        def smembers(self, key):
            return [b"STALE", b"ACTIVE"]

        def srem(self, key, *members):
            self.removed_members.extend(members)

        def delete(self, key):
            self.deleted_keys.append(key)

    fake = _FakeRedis()
    monkeypatch.setattr(
        "app.transport.services.offer_service.redis_client",
        fake,
    )
    monkeypatch.setattr(
        OfferService,
        "get_offer",
        staticmethod(
            lambda booking_ref, driver_id=None:
                None if booking_ref == "STALE" else {"status": "offered"}
        ),
    )

    first = OfferService.sweep_expired_page(batch_size=50)
    assert first["cleared"] == 2
    assert first["driver_cursor"] == -1
    assert first["index_cursor"] == 9
    assert first["has_more"] is True
    assert fake.removed_members == [b"STALE"]
    assert fake.deleted_keys == [b"transport:offer:index:booking:STALE"]
    assert all(count == 50 for _, _, count in fake.scans)

    second = OfferService.sweep_expired_page(
        batch_size=50,
        driver_cursor=first["driver_cursor"],
        index_cursor=first["index_cursor"],
    )
    assert second["has_more"] is False
    assert second["driver_cursor"] == -1
    assert second["index_cursor"] == -1
    assert second["cleared"] == 0
    # Driver SCAN finished on page one and must not restart while the index
    # cursor is still progressing.
    assert sum("transport:driver:" in match for _, match, _ in fake.scans) == 1

def test_transport_permission_purge_is_registered_as_a_celery_task():
    from app.tasks.transport_permission_purge import (
        purge_expired_transport_permissions,
    )

    assert purge_expired_transport_permissions.name == (
        "app.tasks.transport_permission_purge.purge_expired_transport_permissions"
    )
    assert callable(purge_expired_transport_permissions.apply_async)


def test_celery_task_context_is_created_lazily_and_cached(monkeypatch):
    from flask import Flask, current_app, has_app_context

    from app.tasks.context import (
        _get_task_flask_app,
        with_flask_app_context,
    )

    _get_task_flask_app.cache_clear()
    task_app = Flask("celery-task-context-test")
    factory_calls = []

    def _create_app():
        factory_calls.append(True)
        return task_app

    monkeypatch.setattr("app.create_app", _create_app)

    @with_flask_app_context
    def _task():
        assert has_app_context()
        return current_app.name

    assert _task() == "celery-task-context-test"
    assert _task() == "celery-task-context-test"
    assert len(factory_calls) == 1
    assert not has_app_context()

    _get_task_flask_app.cache_clear()


def test_celery_task_context_reuses_existing_context(monkeypatch):
    from flask import Flask, current_app

    from app.tasks.context import (
        _get_task_flask_app,
        with_flask_app_context,
    )

    _get_task_flask_app.cache_clear()
    task_app = Flask("existing-celery-context")
    factory_calls = []

    def _create_app():
        factory_calls.append(True)
        return Flask("unexpected-second-app")

    monkeypatch.setattr("app.create_app", _create_app)

    @with_flask_app_context
    def _task():
        return current_app._get_current_object()

    with task_app.app_context():
        assert _task() is task_app

    assert factory_calls == []
    _get_task_flask_app.cache_clear()


def test_context_required_celery_tasks_keep_the_context_wrapper():
    from app.tasks.cleanup import cleanup_expired_holds
    from app.tasks.accommodation_reminders import (
        send_registration_reminders,
        send_pre_arrival_request_reminder,
        enforce_registration_deadlines,
        expire_unapproved_bookings,
        detect_no_shows,
        notify_incomplete_properties,
    )
    from app.media.tasks import (
        process_media_task,
        process_pending_media,
        cleanup_failed_media,
    )

    tasks = (
        cleanup_expired_holds,
        send_registration_reminders,
        send_pre_arrival_request_reminder,
        enforce_registration_deadlines,
        expire_unapproved_bookings,
        detect_no_shows,
        notify_incomplete_properties,
        process_media_task,
        process_pending_media,
        cleanup_failed_media,
    )

    for task in tasks:
        assert hasattr(task.run, "__wrapped__"), (
            f"{task.name} must retain the Flask-context task wrapper"
        )


def test_cleanup_expired_holds_surfaces_errors_as_task_failures(app, monkeypatch):
    from app import create_app as _original_create_app
    from flask import has_app_context

    from app.accommodation.services.availability_service import AvailabilityService
    from app.tasks.cleanup import cleanup_expired_holds
    from app.tasks.context import _get_task_flask_app

    _get_task_flask_app.cache_clear()
    monkeypatch.setattr("app.create_app", lambda: app)

    def _raise_without_context(**kwargs):
        assert has_app_context()
        raise RuntimeError("simulated hold cleanup database failure")

    monkeypatch.setattr(
        AvailabilityService,
        "release_expired_holds",
        staticmethod(_raise_without_context),
    )

    try:
        with pytest.raises(RuntimeError, match="simulated hold cleanup database failure"):
            cleanup_expired_holds.run()
    finally:
        _get_task_flask_app.cache_clear()
        monkeypatch.setattr("app.create_app", _original_create_app)

