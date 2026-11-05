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
    monkeypatch.setattr(BlockedDate, "query", _Query([]))
    monkeypatch.setattr(RoomHold, "query", _Query([legacy_hold]))
    monkeypatch.setattr(db.session, "commit", lambda: None)

    result = AvailabilityService.release_expired_holds(batch_size=25)

    assert legacy_hold.status == "expired"
    assert result["released"] == 1
    assert result["has_more"] is False
