"""BL-22 behavioral proof: the assigned driver is addressed on assignment.

Transport Booking.assigned_driver_id is a DriverProfile id (written by
AssignmentService.dispatch_claim; see Booking.driver relationship). The
driver branch of notify_driver_assigned must resolve that profile to its
User and address the "New Trip Assigned" notification there — not read
the nonexistent booking.driver_id (which silently notifies nobody).

Proven via the existing hook: transport_driver_assigned signal ->
listener -> notify_driver_assigned. send/_notify_admins are stubbed
(canonical seam); all rows are real.
"""
import uuid
from unittest.mock import patch

import pytest

import app.notifications.listeners  # noqa: F401  (ensure hook connected)

from app.notifications.services import NotificationService
from app.notifications.signals import transport_driver_assigned

pytestmark = pytest.mark.usefixtures("db_session")


def _user(db_session, tag):
    from app.identity.models.user import User

    uid = uuid.uuid4().hex[:8]
    user = User(
        username=f"bl22_{tag}_{uid}",
        email=f"bl22_{tag}_{uid}@example.com",
        is_verified=True,
        is_active=True,
    )
    user.set_password("TestPass123!")
    db_session.add(user)
    db_session.flush()
    return user


def _driver_profile(db_session, user):
    from app.transport.models import (
        ComplianceStatus,
        DriverProfile,
        VerificationTier,
    )

    uid = uuid.uuid4().hex[:8]
    profile = DriverProfile(
        user_id=user.id,
        driver_code=f"BL22-{uid[:6].upper()}",
        verification_tier=VerificationTier.PENDING,
        compliance_status=ComplianceStatus.APPROVED,
        is_active=True,
    )
    db_session.add(profile)
    db_session.flush()
    return profile


def _assigned_booking(db_session, rider, profile):
    from datetime import datetime, timedelta, timezone

    from app.transport.models import (
        Booking,
        BookingStatus,
        ProviderType,
        ServiceType,
    )

    ref = f"TRBL22{uuid.uuid4().hex[:6].upper()}"
    booking = Booking(
        user_id=rider.id,
        booking_reference=ref,
        provider_type=ProviderType.INDIVIDUAL_DRIVER,
        service_type=ServiceType.ON_DEMAND,
        pickup_location={"latitude": 1.2, "longitude": 3.4},
        dropoff_location={"latitude": 5.6, "longitude": 7.8},
        pickup_time=datetime.now(timezone.utc) + timedelta(hours=2),
        passenger_count=1,
        base_price=100.00,
        currency="USD",
        status=BookingStatus.ASSIGNED,
        assigned_driver_id=profile.id,
    )
    db_session.add(booking)
    db_session.flush()
    db_session.commit()
    return booking


def test_bl22_assigned_driver_user_is_notified(app, db_session):
    rider = _user(db_session, "rider")
    driver_user = _user(db_session, "driver")
    profile = _driver_profile(db_session, driver_user)
    booking = _assigned_booking(db_session, rider, profile)
    ref = booking.booking_reference
    driver_uid = driver_user.id
    assert booking.assigned_driver_id != driver_uid  # ids differ: proof is real

    with patch.object(
        NotificationService, "send", autospec=True
    ) as mock_send, patch.object(
        NotificationService, "_notify_admins", autospec=True
    ):
        transport_driver_assigned.send(
            "bl22-test", booking=booking, driver_name="Kato"
        )

    driver_calls = [
        c
        for c in mock_send.call_args_list
        if c.kwargs.get("user_id") == driver_uid
    ]
    assert driver_calls, (
        "assigned driver user received no notification "
        f"(calls went to {[c.kwargs.get('user_id') for c in mock_send.call_args_list]})"
    )
    assert driver_calls[0].kwargs["data"]["booking_id"] == ref
