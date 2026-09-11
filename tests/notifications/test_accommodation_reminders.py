#!/usr/bin/env python
"""Regression tests for accommodation reminder notification types.

Guards the legacy-type silent-drop fix: the scheduled registration-reminder
tasks must emit canonical NotificationType/NotificationModule values and
produce a persisted Notification row instead of being silently dropped.
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.notifications.models import (
    Notification,
    NotificationModule,
    NotificationType,
)
from app.notifications.services import NotificationService
from app.tasks.accommodation_reminders import send_registration_reminders


def test_registration_reminders_emit_canonical_type_and_module(monkeypatch):
    """The hourly registration-reminder task must not pass legacy type strings."""
    from unittest.mock import MagicMock

    from app.accommodation.models.booking import AccommodationBooking

    calls = []

    def fake_send(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(NotificationService, "send", fake_send)
    monkeypatch.setattr(
        "app.tasks.accommodation_reminders._is_fully_registered",
        lambda booking_id: False,
    )

    def make_booking(ref):
        return SimpleNamespace(
            id=len(calls) + 1,
            booking_owner_id=None,
            booked_by_user_id=1001,
            booking_reference=ref,
            check_in=datetime.now(timezone.utc),
        )

    mock_query = MagicMock()
    mock_query.filter.return_value.all.side_effect = [
        [make_booking("BK-72H")],
        [make_booking("BK-48H")],
        [make_booking("BK-24H")],
        [make_booking("BK-POST")],
    ]
    monkeypatch.setattr(AccommodationBooking, "query", mock_query)

    send_registration_reminders()

    assert len(calls) == 4
    for call in calls:
        assert call["notification_type"] == NotificationType.BOOKING_UPDATE
        assert call["module"] == NotificationModule.ACCOMMODATION
        assert call["user_id"] == 1001


def test_booking_update_notification_persists_accommodation_module(db_session):
    """BOOKING_UPDATE + ACCOMMODATION flows through the unified service into a row."""
    from werkzeug.security import generate_password_hash

    from app.identity.models.user import User

    user = User(
        username=f"reminder_{uuid.uuid4().hex[:8]}",
        email=f"reminder_{uuid.uuid4().hex[:8]}@example.com",
    )
    user.password_hash = generate_password_hash("test_password")
    db_session.add(user)
    db_session.flush()

    notification = NotificationService.send(
        user_id=user.id,
        notification_type=NotificationType.BOOKING_UPDATE,
        module=NotificationModule.ACCOMMODATION,
        title="A few days until your stay",
        message="Anything we should know?",
        channels=["in_app"],
        data={"booking_reference": "BK-SPECIAL"},
    )

    assert notification is not None
    assert notification.type == NotificationType.BOOKING_UPDATE.value
    assert notification.module == NotificationModule.ACCOMMODATION.value
    assert notification.user_id == user.id
    persisted = Notification.query.filter_by(
        user_id=user.id,
        type=NotificationType.BOOKING_UPDATE.value,
        module=NotificationModule.ACCOMMODATION.value,
    ).first()
    assert persisted is not None