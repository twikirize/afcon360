# app/events/settings_model.py
"""
EventSettings — platform-wide event configuration.

Single-row table.  Never insert more than one row.
Use EventSettings.get() everywhere — it caches in Redis and falls back
to DB on cache miss.

Usage:
    from app.events.settings_model import EventSettings
    settings = EventSettings.get()
    if settings.auto_publish:
        ...
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import Column, Integer, Boolean, String, DateTime, Text
from app.extensions import db
from app.models.base import BaseModel

log = logging.getLogger(__name__)

_CACHE_KEY  = "platform:event_settings"
_CACHE_TTL  = 300   # 5 minutes


class EventSettings(BaseModel):
    """
    Platform-wide event settings.  One row only — use EventSettings.get().

    All settings have safe defaults so the system works even before
    the admin has visited the settings page.
    """
    __tablename__ = "event_settings"

    # ── Approval workflow ──────────────────────────────────────────────────
    auto_publish = Column(
        Boolean, default=False, nullable=False,
        doc="Skip moderation — new events go straight to PUBLISHED."
    )
    require_approval = Column(
        Boolean, default=True, nullable=False,
        doc="All events must pass moderation before publishing."
    )
    event_manager_auto_approve = Column(
        Boolean, default=True, nullable=False,
        doc="Events created by event_manager role are auto-approved."
    )

    # ── Capacity & registration ────────────────────────────────────────────
    allow_free_events = Column(
        Boolean, default=True, nullable=False,
        doc="Allow events with zero-price tickets."
    )
    max_capacity_limit = Column(
        Integer, default=0, nullable=False,
        doc="Platform-wide cap on event capacity.  0 = unlimited."
    )
    registration_open_days_before = Column(
        Integer, default=0, nullable=False,
        doc="How many days before start_date registrations open.  0 = immediately."
    )

    # ── Lifecycle automation ───────────────────────────────────────────────
    auto_complete_events = Column(
        Boolean, default=True, nullable=False,
        doc="Scheduler auto-transitions PUBLISHED → COMPLETED after end_date."
    )
    auto_archive_after_days = Column(
        Integer, default=90, nullable=False,
        doc="Days after COMPLETED/CANCELLED before auto-archive.  0 = never."
    )
    allow_organiser_cancel = Column(
        Boolean, default=True, nullable=False,
        doc="Organisers can cancel their own PUBLISHED events."
    )
    allow_organiser_delete = Column(
        Boolean, default=True, nullable=False,
        doc="Organisers can soft-delete (→ ARCHIVED) their own events."
    )

    # ── Notifications ──────────────────────────────────────────────────────
    notify_admin_on_submit = Column(
        Boolean, default=True, nullable=False,
        doc="Email platform admins when an event is submitted for approval."
    )
    notify_organiser_on_decision = Column(
        Boolean, default=True, nullable=False,
        doc="Email organiser when their event is approved or rejected."
    )
    notify_organiser_on_suspend = Column(
        Boolean, default=True, nullable=False,
        doc="Email organiser when their event is suspended."
    )

    # ── Ticket controls ────────────────────────────────────────────────────
    allow_multiple_ticket_types = Column(
        Boolean, default=True, nullable=False,
        doc="Allow events to have more than one ticket type."
    )
    max_ticket_types_per_event = Column(
        Integer, default=10, nullable=False,
        doc="Maximum number of ticket types per event.  0 = unlimited."
    )
    allow_discount_codes = Column(
        Boolean, default=True, nullable=False,
        doc="Allow organisers to create discount codes for their events."
    )

    # ── Display ────────────────────────────────────────────────────────────
    show_attendee_count = Column(
        Boolean, default=True, nullable=False,
        doc="Show registration count on public event pages."
    )
    show_remaining_capacity = Column(
        Boolean, default=False, nullable=False,
        doc="Show remaining seats on public event pages."
    )

    # ── Meta ───────────────────────────────────────────────────────────────
    updated_by_id = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True,
                   doc="Internal notes about current settings configuration.")

    # ── Class methods ──────────────────────────────────────────────────────

    @classmethod
    def get(cls) -> "EventSettings":
        """
        Return the singleton settings row, creating it with defaults if
        it doesn't exist yet.  Caches in Redis for 5 minutes.
        """
        # Try Redis cache first
        try:
            from app.extensions import redis_client
            if redis_client:
                cached = redis_client.get(_CACHE_KEY)
                if cached:
                    data = json.loads(cached)
                    obj = cls()
                    for k, v in data.items():
                        if hasattr(obj, k):
                            setattr(obj, k, v)
                    return obj
        except Exception as e:
            log.debug(f"EventSettings cache miss: {e}")

        # Fall back to DB
        row = cls.query.first()
        if not row:
            row = cls()
            db.session.add(row)
            try:
                db.session.commit()
                log.info("EventSettings: created default settings row")
            except Exception:
                db.session.rollback()
                row = cls.query.first() or cls()

        # Cache it
        cls._cache(row)
        return row

    @classmethod
    def _cache(cls, row: "EventSettings"):
        """Write settings to Redis cache."""
        try:
            from app.extensions import redis_client
            if redis_client:
                data = {
                    c.key: getattr(row, c.key)
                    for c in cls.__table__.columns
                    if not c.key.startswith('_')
                }
                redis_client.setex(_CACHE_KEY, _CACHE_TTL, json.dumps(data, default=str))
        except Exception as e:
            log.debug(f"EventSettings cache write failed: {e}")

    @classmethod
    def invalidate_cache(cls):
        """Clear the Redis cache — call after saving changes."""
        try:
            from app.extensions import redis_client
            if redis_client:
                redis_client.delete(_CACHE_KEY)
        except Exception:
            pass

    def save(self, updated_by_id: int = None):
        """Persist changes and invalidate cache."""
        if updated_by_id:
            self.updated_by_id = updated_by_id
        try:
            db.session.commit()
            self.__class__.invalidate_cache()
            log.info(f"EventSettings updated by user {updated_by_id}")
            return True, None
        except Exception as e:
            db.session.rollback()
            log.error(f"EventSettings save failed: {e}")
            return False, str(e)

    def __repr__(self):
        return (
            f"<EventSettings auto_publish={self.auto_publish} "
            f"require_approval={self.require_approval}>"
        )