"""AFCON360-BATCH-3-FINAL-PACKAGE — focused verification coverage.

Scope-locked to the three authorized findings only:

  P-14a   rider incident creation route accessibility
          (app/transport/routes.py :: _PUBLIC_ENDPOINTS += transport.incidents_new)
  D-11    soft-deleted booking must not retain assignment references
          (app/transport/api/booking_routes.py :: BookingDetailResource.delete)
  F-NEW-A `User` runtime NameError in NotificationService.resend_failed
          (app/notifications/services.py :: local runtime import)

No migration, no schema change, no shared-fixture modification.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.extensions import db


# =====================================================================
# Shared seeding helpers (uuid-suffixed: never collide with committed rows)
# =====================================================================

def _create_user(app, label="b3"):
    from app.identity.models.user import User
    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        u = User(
            username=f"{label}_{uid}",
            email=f"{label}_{uid}@test.example.com",
            is_verified=True,
            is_active=True,
        )
        u.set_password("TestPass123!")
        db.session.add(u)
        db.session.commit()
        return u.id


def _create_driver(app, label="b3drv"):
    from app.transport.models import ComplianceStatus, DriverProfile
    user_id = _create_user(app, f"drv_{label}")
    with app.app_context():
        dp = DriverProfile(
            user_id=user_id,
            driver_code=f"B3-{label}-{uuid.uuid4().hex[:6].upper()}",
            verification_tier="platform_verified",
            compliance_status=ComplianceStatus.APPROVED,
            is_active=True, is_online=True, is_available=True,
            max_passenger_capacity=4, vehicle_classes=["comfort"],
        )
        db.session.add(dp)
        db.session.commit()
        return user_id, dp.id


def _create_vehicle(app, driver_id, label="b3v"):
    from app.transport.models import Vehicle, VehicleClass
    with app.app_context():
        v = Vehicle(
            owner_type="driver", owner_id=driver_id,
            license_plate=f"UG-{label}-{uuid.uuid4().hex[:4].upper()}",
            make="Toyota", model="Corolla", year=2022,
            vehicle_type="sedan", vehicle_class=VehicleClass.COMFORT,
            passenger_capacity=4, status="active", is_available=True,
        )
        db.session.add(v)
        db.session.commit()
        return v.id


def _create_booking(app, user_id, label="b3bk", status=None,
                    driver_id=None, vehicle_id=None):
    from app.transport.models import (
        Booking, BookingStatus, ProviderType, ServiceType,
    )
    with app.app_context():
        now = datetime.now(timezone.utc)
        ref = f"B3-{label}-{uuid.uuid4().hex[:8].upper()}"
        bk = Booking(
            booking_reference=ref, user_id=user_id,
            provider_type=ProviderType.INDIVIDUAL_DRIVER,
            service_type=ServiceType.ON_DEMAND,
            pickup_location={"latitude": 0.3476, "longitude": 32.5825},
            dropoff_location={"latitude": 0.3130, "longitude": 32.5812},
            pickup_time=now + timedelta(hours=2),
            passenger_count=1, base_price=Decimal("10.00"),
            subtotal=Decimal("10.00"), total_amount=Decimal("10.00"),
            final_price=Decimal("10.00"),
            status=status or BookingStatus.CONFIRMED,
            assigned_driver_id=driver_id,
            assigned_vehicle_id=vehicle_id,
        )
        db.session.add(bk)
        db.session.commit()
        return bk.id, ref


# =====================================================================
# P-14a — rider incident creation accessibility
# =====================================================================

class TestP14aIncidentCreationAccessibility:
    def test_incidents_new_in_public_endpoints(self, app):
        """Set membership: the rider-facing incident form must pass the
        coarse before_request permission hook."""
        with app.app_context():
            from app.transport.routes import _PUBLIC_ENDPOINTS
            assert "transport.incidents_new" in _PUBLIC_ENDPOINTS

    def test_rider_get_incidents_new_200(self, app, authenticated_client):
        """Non-admin rider reaches the incident form (HTTP 200, no
        permission-hook redirect to the transport home page)."""
        resp = authenticated_client.get("/transport/incidents/new")
        assert resp.status_code == 200, (
            f"rider blocked from incident form: {resp.status_code} -> "
            f"{resp.headers.get('Location', '')}"
        )

    def test_admin_get_incidents_new_200(self, app, admin_client):
        resp = admin_client.get("/transport/incidents/new")
        assert resp.status_code == 200

    def test_unauthenticated_get_incidents_new_redirects_to_login(
        self, app, client
    ):
        resp = client.get("/transport/incidents/new",
                          follow_redirects=False)
        assert resp.status_code in (301, 302), resp.status_code
        assert "login" in resp.headers.get("Location", "").lower(), (
            resp.headers.get("Location", "")
        )


# =====================================================================
# D-11 — soft-deleted booking must not retain assignment references
# =====================================================================

class TestD11SoftDeleteClearsAssignmentRefs:
    def test_completed_booking_with_stale_refs_cleared(
        self, app, admin_client
    ):
        """Case A: COMPLETED booking carrying stale assignment refs —
        DELETE succeeds and clears both refs plus the soft-delete flags."""
        from app.transport.models import Booking, BookingStatus
        _, driver_id = _create_driver(app, "d11a")
        vehicle_id = _create_vehicle(app, driver_id, "d11a")
        rider_id = _create_user(app, "d11a_rider")
        _, ref = _create_booking(
            app, rider_id, "d11a", status=BookingStatus.COMPLETED,
            driver_id=driver_id, vehicle_id=vehicle_id,
        )

        resp = admin_client.delete(f"/api/transport/bookings/{ref}")
        assert resp.status_code == 200, resp.get_data(as_text=True)

        with app.app_context():
            bk = Booking.query.filter_by(booking_reference=ref).first()
            assert bk is not None
            assert bk.is_deleted is True
            assert bk.deleted_at is not None
            assert bk.assigned_driver_id is None
            assert bk.assigned_vehicle_id is None

    def test_active_booking_still_rejected_409(self, app, admin_client):
        """Case B: a booking in a genuinely active assignment status
        (ASSIGNED ∈ ACTIVE_ASSIGNMENT_STATUSES) is still rejected with
        409/active_assignment and left unchanged.

        Note: CONFIRMED is *not* in ACTIVE_ASSIGNMENT_STATUSES (canonical
        single source of truth in assignment_service), so the live-status
        representative used here is ASSIGNED.
        """
        from app.transport.models import Booking, BookingStatus
        _, driver_id = _create_driver(app, "d11b")
        vehicle_id = _create_vehicle(app, driver_id, "d11b")
        rider_id = _create_user(app, "d11b_rider")
        _, ref = _create_booking(
            app, rider_id, "d11b", status=BookingStatus.ASSIGNED,
            driver_id=driver_id, vehicle_id=vehicle_id,
        )

        resp = admin_client.delete(f"/api/transport/bookings/{ref}")
        assert resp.status_code == 409, resp.get_data(as_text=True)
        assert resp.get_json().get("code") == "active_assignment"

        with app.app_context():
            bk = Booking.query.filter_by(booking_reference=ref).first()
            assert bk is not None
            assert bk.is_deleted is False
            assert bk.assigned_driver_id == driver_id
            assert bk.assigned_vehicle_id == vehicle_id

    def test_terminal_booking_without_refs_untouched_fields(
        self, app, admin_client
    ):
        """Case C: terminal booking without assignment refs — DELETE
        succeeds and unrelated fields are preserved."""
        from app.transport.models import Booking, BookingStatus
        rider_id = _create_user(app, "d11c_rider")
        _, ref = _create_booking(
            app, rider_id, "d11c", status=BookingStatus.COMPLETED,
        )
        with app.app_context():
            before = Booking.query.filter_by(
                booking_reference=ref).first()
            snapshot = {
                "user_id": before.user_id,
                "status": before.status,
                "total": str(before.total_amount),
                "price": str(before.final_price),
                "ref": before.booking_reference,
            }

        resp = admin_client.delete(f"/api/transport/bookings/{ref}")
        assert resp.status_code == 200, resp.get_data(as_text=True)

        with app.app_context():
            after = Booking.query.filter_by(
                booking_reference=ref).first()
            assert after.is_deleted is True
            assert after.user_id == snapshot["user_id"]
            assert after.status == snapshot["status"]
            assert str(after.total_amount) == snapshot["total"]
            assert str(after.final_price) == snapshot["price"]
            assert after.booking_reference == snapshot["ref"]

    def test_followup_claim_reuses_driver_after_stale_delete(
        self, app, admin_client
    ):
        """Runtime follow-up: after deleting a stale COMPLETED booking,
        the same driver is claimable on a fresh CONFIRMED booking via the
        canonical AssignmentService.claim path."""
        from app.transport.models import Booking, BookingStatus
        from app.transport.services.assignment_service import (
            AssignmentService,
        )
        _, driver_id = _create_driver(app, "d11f")
        vehicle_id = _create_vehicle(app, driver_id, "d11f")
        rider_id = _create_user(app, "d11f_rider")
        _, stale_ref = _create_booking(
            app, rider_id, "d11f_stale",
            status=BookingStatus.COMPLETED,
            driver_id=driver_id, vehicle_id=vehicle_id,
        )
        resp = admin_client.delete(
            f"/api/transport/bookings/{stale_ref}")
        assert resp.status_code == 200, resp.get_data(as_text=True)

        _, fresh_ref = _create_booking(
            app, rider_id, "d11f_fresh",
            status=BookingStatus.CONFIRMED,
        )
        with app.app_context():
            result = AssignmentService.claim(
                fresh_ref, driver_id, vehicle_id, actor=None)
        assert result.get("status") == BookingStatus.ASSIGNED.value, result
        assert result.get("driver_id") == driver_id, result
        with app.app_context():
            fresh = Booking.query.filter_by(
                booking_reference=fresh_ref).first()
            assert fresh.assigned_driver_id == driver_id
            assert fresh.assigned_vehicle_id == vehicle_id
            assert fresh.status == BookingStatus.ASSIGNED.value


# =====================================================================
# F-NEW-A — resend_failed must not raise NameError for `User`
# =====================================================================

class TestFNewAResendFailed:
    def test_resend_failed_in_app_row(self, app, db_session):
        """Seed FAILED/IN_APP/attempts=0; resend_failed() must raise no
        NameError, count the row, bump attempts, and move it off FAILED
        via the existing InAppHandler success path."""
        import uuid as _uuid
        from app.identity.models.user import User
        from app.notifications.models import (
            Notification, NotificationChannel, NotificationStatus,
            NotificationType,
        )
        from app.notifications.services import NotificationService

        user = User(
            public_id=str(_uuid.uuid4()),
            email=f"fnewa-{_uuid.uuid4().hex[:8]}@example.com",
            username=f"fnewa-{_uuid.uuid4().hex[:6]}",
            password_hash="dummy-hash",
            is_verified=True,
            is_active=True,
        )
        db_session.add(user)
        db_session.flush()
        notification = Notification(
            user_id=user.id,
            type=NotificationType.BOOKING_CONFIRMED,
            channel=NotificationChannel.IN_APP,
            subject="F-NEW-A proof",
            body="resend must not NameError on User",
            status=NotificationStatus.FAILED,
            attempts=0,
        )
        db_session.add(notification)
        db_session.commit()
        notif_id = notification.id

        count = NotificationService.resend_failed()  # must not NameError

        assert count >= 1, "resend_failed did not count the FAILED row"
        db_session.expire_all()
        row = db_session.get(Notification, notif_id)
        assert row.attempts == 1, row.attempts
        assert row.status != NotificationStatus.FAILED, row.status
