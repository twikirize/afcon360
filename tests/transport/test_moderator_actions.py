"""T-10 behavioral proof: moderate_action writes real columns / delegates.

The old body wrote verification_status / verified_at / rejection_reason,
none of which are columns on Vehicle or DriverProfile, so approve/reject
committed nothing (with a success flash). The fix (Option B, ratified):

- vehicle approve/reject writes real columns directly (item.status ->
  'active' / 'rejected'), with hasattr guards for verified_at /
  rejection_reason (matching the admin moderator twin).
- driver approve/reject delegates to
  ProviderService.update_driver_status (same implementation the admin
  approve routes use).
- The Booking branch is unchanged by design.

provider.py's update_vehicle_status permission gate is NOT touched in this
node; vehicle does not delegate to it.
"""
import uuid

import pytest

pytestmark = pytest.mark.usefixtures("db_session")


def _moderator_public_id(app, db_session):
    from app.identity.models.roles_permission import Role
    from app.identity.models.user import User, UserRole

    uid = uuid.uuid4().hex[:8]
    mod = User(
        username=f"mod_{uid}",
        email=f"mod_{uid}@example.com",
        is_verified=True,
        is_active=True,
    )
    mod.set_password("TestPass123!")
    db_session.add(mod)
    db_session.flush()
    # Moderator role only: require_moderator passes it, and the moderate
    # endpoints are public past the coarse before_request gate (2a), so
    # no admin role is needed to reach moderate_action.
    role = Role.query.filter_by(name="moderator").first()
    if role is None:
        role = Role(name="moderator", scope="global")
        db_session.add(role)
        db_session.flush()
    db_session.add(UserRole(user_id=mod.id, role_id=role.id))
    db_session.commit()
    return mod.public_id


def _mod_client(client, public_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = public_id
        sess["_fresh"] = True
    return client


def _vehicle(db_session, status="pending"):
    from app.transport.models import Vehicle

    uid = uuid.uuid4().hex[:8].upper()
    v = Vehicle(
        owner_type="driver",
        owner_id=1,
        license_plate=f"UG{uid}",
        make="Test",
        model="Model",
        year=2023,
        vehicle_type="Sedan",
        vehicle_class="comfort",
        passenger_capacity=4,
        current_location={"latitude": 1.2, "longitude": 3.4},
        status=status,
    )
    db_session.add(v)
    db_session.flush()
    db_session.commit()
    return v


def _driver(db_session):
    from app.identity.models.user import User
    from app.transport.models import ComplianceStatus, DriverProfile, VerificationTier

    uid = uuid.uuid4().hex[:8]
    user = User(
        username=f"drv_{uid}",
        email=f"drv_{uid}@example.com",
        is_verified=True,
        is_active=True,
    )
    user.set_password("TestPass123!")
    db_session.add(user)
    db_session.flush()
    profile = DriverProfile(
        user_id=user.id,
        driver_code=f"MD-{uid[:6].upper()}",
        verification_tier=VerificationTier.PENDING,
        compliance_status=ComplianceStatus.PENDING_REVIEW,
        is_active=True,
        vehicle_classes=["comfort"],
    )
    db_session.add(profile)
    db_session.flush()
    db_session.commit()
    return profile


def _booking(db_session):
    from datetime import datetime, timedelta, timezone

    from app.identity.models.user import User
    from app.transport.models import (
        Booking,
        ProviderType,
        ServiceType,
    )

    uid = uuid.uuid4().hex[:8]
    booker = User(
        username=f"bkr_{uid}",
        email=f"bkr_{uid}@example.com",
        is_verified=True,
        is_active=True,
    )
    booker.set_password("TestPass123!")
    db_session.add(booker)
    db_session.flush()
    booking = Booking(
        user_id=booker.id,
        provider_type=ProviderType.INDIVIDUAL_DRIVER,
        service_type=ServiceType.ON_DEMAND,
        pickup_location={"latitude": 1.2, "longitude": 3.4},
        dropoff_location={"latitude": 5.6, "longitude": 7.8},
        pickup_time=datetime.now(timezone.utc) + timedelta(hours=2),
        passenger_count=1,
        base_price=100.00,
        currency="USD",
        status="pending_payment",
    )
    db_session.add(booking)
    db_session.flush()
    db_session.commit()
    return booking


def test_moderate_vehicle_writes_status_directly(app, client, db_session):
    from app.transport.models import Vehicle

    vehicle = _vehicle(db_session, status="pending")
    vid = vehicle.id
    _authed = _mod_client(client, _moderator_public_id(app, db_session))

    resp = _authed.post(
        f"/transport/moderate/vehicle/{vid}/approve", follow_redirects=False
    )
    assert resp.status_code == 302
    db_session.expire_all()
    assert db_session.get(Vehicle, vid).status == "active"

    resp = _authed.post(
        f"/transport/moderate/vehicle/{vid}/reject",
        data={"reason": "duplicate listing"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    db_session.expire_all()
    assert db_session.get(Vehicle, vid).status == "rejected"


def test_moderate_driver_approve_delegates_to_service(
    app, client, db_session
):
    from app.transport.models import ComplianceStatus, DriverProfile

    profile = _driver(db_session)
    pid = profile.id
    _authed = _mod_client(client, _moderator_public_id(app, db_session))

    resp = _authed.post(
        f"/transport/moderate/driver/{pid}/approve", follow_redirects=False
    )
    assert resp.status_code == 302
    db_session.expire_all()
    assert (
        db_session.get(DriverProfile, pid).compliance_status
        == ComplianceStatus.APPROVED
    )


def test_moderate_booking_approve_unchanged(app, client, db_session):
    from app.transport.models import Booking, BookingStatus

    booking = _booking(db_session)
    bid = booking.id
    _authed = _mod_client(client, _moderator_public_id(app, db_session))

    resp = _authed.post(
        f"/transport/moderate/booking/{bid}/approve", follow_redirects=False
    )
    assert resp.status_code == 302
    db_session.expire_all()
    assert db_session.get(Booking, bid).status == BookingStatus.CONFIRMED


# --- BL-19: vehicle/driver rejection reason accepted but not persisted ---
#
# Vehicle has no rejection_reason column and
# ProviderService.update_driver_status has no reason parameter, so the
# required reason textarea on the vehicle/driver reject forms is
# mandatory-but-discarded. Fix (backlog option b): remove the reason
# field from the vehicle/driver reject forms and stop requiring it for
# those entity types. Booking (cancellation_reason) and flag
# (create_flag) paths persist the reason and are unchanged.


def test_bl19_vehicle_reject_without_reason_persists(
    app, client, db_session
):
    from app.transport.models import Vehicle

    vehicle = _vehicle(db_session, status="pending")
    vid = vehicle.id
    _authed = _mod_client(client, _moderator_public_id(app, db_session))

    resp = _authed.post(
        f"/transport/moderate/vehicle/{vid}/reject",
        data={},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    db_session.expire_all()
    assert db_session.get(Vehicle, vid).status == "rejected"


def test_bl19_driver_reject_without_reason_persists(
    app, client, db_session
):
    from app.transport.models import ComplianceStatus, DriverProfile

    profile = _driver(db_session)
    pid = profile.id
    _authed = _mod_client(client, _moderator_public_id(app, db_session))

    resp = _authed.post(
        f"/transport/moderate/driver/{pid}/reject",
        data={},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    db_session.expire_all()
    assert (
        db_session.get(DriverProfile, pid).compliance_status
        == ComplianceStatus.REVOKED
    )


def test_bl19_reject_forms_have_no_reason_field(app, client, db_session):
    vid = _vehicle(db_session, status="pending").id
    pid = _driver(db_session).id
    _authed = _mod_client(client, _moderator_public_id(app, db_session))

    resp = _authed.get(f"/transport/moderate/vehicle/{vid}")
    assert resp.status_code == 200
    assert b"Rejection Reason" not in resp.data
    assert b"Flag for Review" in resp.data

    resp = _authed.get(f"/transport/moderate/driver/{pid}")
    assert resp.status_code == 200
    assert b"Rejection Reason" not in resp.data
    assert b"Flag for Review" in resp.data


def test_bl19_booking_reject_still_requires_and_persists_reason(
    app, client, db_session
):
    from app.transport.models import Booking, BookingStatus

    booking = _booking(db_session)
    bid = booking.id
    _authed = _mod_client(client, _moderator_public_id(app, db_session))

    resp = _authed.post(
        f"/transport/moderate/booking/{bid}/reject",
        data={},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    db_session.expire_all()
    assert db_session.get(Booking, bid).status != BookingStatus.CANCELLED

    resp = _authed.post(
        f"/transport/moderate/booking/{bid}/reject",
        data={"reason": "duplicate request"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    db_session.expire_all()
    rejected = db_session.get(Booking, bid)
    assert rejected.status == BookingStatus.CANCELLED
    assert rejected.cancellation_reason == "duplicate request"