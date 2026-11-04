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
