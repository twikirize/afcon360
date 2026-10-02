"""SUPPLY-00 regression test for AssignmentService claim/release invariant.

Under the corrected semantic model (SUPPLY-00):
- is_available means "qualified to drive" (set at approval, cleared at
  suspension/revocation)
- is_online means "actively dispatch-ready"
- claim()/release() NEVER touch driver.is_available - it is a qualification
  flag, not a busy flag
- Vehicle.is_available IS a legitimate "not on trip" flag and IS toggled
"""
import pytest

from app.extensions import db
from app.identity.models.user import User
from app.transport.models import (
    Booking,
    BookingStatus,
    DriverProfile,
    DriverVehicleHistory,
    Vehicle,
)
from app.transport.services.assignment_service import AssignmentService
from tests.test_transport_concurrent_claim import (
    _create_user,
    _create_booking,
    _make_matchable_driver,
    _delete,
)


def _clear_notifications_for(app, *user_ids):
    """Clear notification_logs -> notifications for users (FK chain)."""
    with app.app_context():
        from app.notifications.models import Notification, NotificationLog
        notif_ids = [
            n.id for n in Notification.query.filter(
                Notification.user_id.in_(list(user_ids))
            ).all()
        ]
        if notif_ids:
            NotificationLog.query.filter(
                NotificationLog.notification_id.in_(notif_ids)
            ).delete(synchronize_session=False)
            Notification.query.filter(
                Notification.id.in_(notif_ids)
            ).delete(synchronize_session=False)
            db.session.commit()


def _make_assigned_booking(app, driver_online: bool):
    """Create a booking in ASSIGNED state with a driver/vehicle."""
    pax_id = _create_user(app, f"pax_{'on' if driver_online else 'off'}")
    user_id, drv, veh, hist = _make_matchable_driver(app, f"{'on' if driver_online else 'off'}")
    bk_id, bk_ref = _create_booking(app, pax_id, "inv")
    AssignmentService.claim(bk_ref, drv, veh, actor=None)
    if not driver_online:
        with app.app_context():
            d = db.session.get(DriverProfile, drv)
            d.is_online = False
            db.session.commit()
    return bk_id, drv, veh, hist, user_id, pax_id


@pytest.mark.parametrize("driver_online", [True, False])
def test_claim_release_preserves_driver_is_available(app, driver_online):
    """release() must never modify driver.is_available (both online states)."""
    booking_id, driver_id, vehicle_id, hist_id, user_id, pax_id = _make_assigned_booking(
        app, driver_online
    )

    with app.app_context():
        before = db.session.get(DriverProfile, driver_id).is_available

    AssignmentService.release(booking_id, BookingStatus.COMPLETED)

    with app.app_context():
        driver = db.session.get(DriverProfile, driver_id)
        vehicle = db.session.get(Vehicle, vehicle_id)
        assert driver.is_available is before
        assert vehicle.is_available is True

    _clear_notifications_for(app, user_id, pax_id)
    _delete(
        app,
        (DriverVehicleHistory, hist_id),
        (Booking, booking_id),
        (DriverProfile, driver_id),
        (Vehicle, vehicle_id),
        (User, user_id),
        (User, pax_id),
    )


def test_claim_sets_vehicle_unavailable(app):
    """claim() sets vehicle.is_available=False (legitimate busy flag)."""
    booking_id, driver_id, vehicle_id, hist_id, user_id, pax_id = _make_assigned_booking(
        app, True
    )

    with app.app_context():
        assert db.session.get(Vehicle, vehicle_id).is_available is False
        assert db.session.get(DriverProfile, driver_id).is_available is True

    AssignmentService.release(booking_id, BookingStatus.COMPLETED)

    _clear_notifications_for(app, user_id, pax_id)
    _delete(
        app,
        (DriverVehicleHistory, hist_id),
        (Booking, booking_id),
        (DriverProfile, driver_id),
        (Vehicle, vehicle_id),
        (User, user_id),
        (User, pax_id),
    )
