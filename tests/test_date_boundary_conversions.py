# tests/test_date_boundary_conversions.py
"""Minimal-targeted tests for the four date-boundary conversions identified as
PROVEN DEFECTIVE in the EGGE audit:

  A. Guest date_of_birth - accommodation guest registration route
     (was: raw form string assigned to a Date column)
  B. Incident occurred_at - /api/transport/incidents
     (was: raw string assigned to timestamptz; DB session timezone decided
     interpretation of naive strings)
  C. Vehicle maintenance dates x4 - /api/transport/vehicles/<id>/maintenance
     (was: raw strings assigned to timestamptz columns)
  D. Organisation insurance_expiry - /api/transport/organisations/<id>
     (was: raw string assigned to a timestamptz column)

Each test asserts the REQUIRED conversion behavior and proves application
behavior through the HTTP boundary (no ORM-level shortcuts for the write).

Notes on test mechanics:
  - Fixture ORM instances may be expired/detached once a request context has
    run, so each test copies the PKs it needs to plain ids up front.
  - timestamptz columns are ECHOED BACK in the PostgreSQL session timezone
    (Africa/Nairobi, +03:00), so read-back datetimes are normalized to UTC
    before instant assertions.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.extensions import db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _login(client, user):
    """Authenticate as the given user via the Flask-Login session cookie."""
    with client.application.app_context():
        merged = db.session.merge(user)
        public_id = str(merged.public_id)
        db.session.rollback()
    with client.session_transaction() as sess:
        sess["_user_id"] = public_id
        sess["_fresh"] = True


def _utc(dt):
    """Normalize an aware datetime to UTC for instant assertions."""
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def guest_user(db_session):
    from app.identity.models.user import User

    user = User(
        public_id=str(uuid.uuid4()),
        username=f"guest_{uuid.uuid4().hex[:8]}",
        email=f"guest_{uuid.uuid4().hex[:8]}@example.com",
        is_verified=True,
        is_active=True,
        email_verified=True,
    )
    user.set_password("Password1!")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def admin_user(db_session):
    from app.identity.models.roles_permission import get_or_create_role
    from app.identity.models.user import User, UserRole

    user = User(
        public_id=str(uuid.uuid4()),
        username=f"admin_{uuid.uuid4().hex[:8]}",
        email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
        is_verified=True,
        is_active=True,
        email_verified=True,
        is_super_admin=True,
    )
    user.set_password("Password1!")
    db.session.add(user)
    db.session.commit()
    role = get_or_create_role("admin", level=3)
    if not any(getattr(r, "role_id", None) == role.id for r in user.roles):
        db.session.add(UserRole(user_id=user.id, role_id=role.id))
        db.session.commit()
    return user


@pytest.fixture
def test_property(db_session, guest_user):
    from app.accommodation.models.property import (
        AccommodationCancellationPolicy,
        Property,
    )

    prop = Property(
        title="Test DOB Property",
        slug=f"dob-prop-{uuid.uuid4().hex[:8]}",
        description="Property for DOB boundary tests",
        address_line1="1 Test Street",
        city="Kampala",
        country="UG",
        status="active",
        is_verified=True,
        is_active=True,
        base_price_per_night=100,
        currency="USD",
        max_guests=2,
        instant_book=True,
        cancellation_policy=AccommodationCancellationPolicy.FLEXIBLE.value,
        owner_user_id=guest_user.id,
    )
    db.session.add(prop)
    db.session.commit()
    return prop


@pytest.fixture
def confirmed_booking(db_session, guest_user, test_property):
    from app.accommodation.models.booking import (
        AccommodationBooking,
        AccommodationBookingStatus,
        AccommodationPaymentStatus,
    )

    today = date.today()
    booking = AccommodationBooking(
        booking_reference=f"DOB-TEST-{uuid.uuid4().hex[:8]}",
        property_id=test_property.id,
        booked_by_user_id=guest_user.id,
        host_user_id=guest_user.id,
        primary_guest_id=guest_user.id,
        guest_user_id=guest_user.id,
        status=AccommodationBookingStatus.CONFIRMED.value,
        payment_status=AccommodationPaymentStatus.PAID.value,
        check_in=today + timedelta(days=3),
        check_out=today + timedelta(days=5),
        num_nights=2,
        nightly_rate=100,
        total_amount=200,
        num_guests=1,
        rooms_requested=1,
    )
    db.session.add(booking)
    db.session.commit()
    return booking


@pytest.fixture
def test_vehicle(db_session, admin_user):
    from app.transport.models import Vehicle, VehicleClass

    vehicle = Vehicle(
        owner_type="individual",
        owner_id=admin_user.id,
        license_plate=f"UG-{uuid.uuid4().hex[:5].upper()}",
        make="Toyota",
        model="Hiace",
        year=2024,
        vehicle_type="van",
        vehicle_class=VehicleClass.VAN,
        passenger_capacity=14,
        status="active",
        is_available=True,
    )
    db.session.add(vehicle)
    db.session.commit()
    return vehicle


@pytest.fixture
def test_organisation(db_session, admin_user):
    from app.identity.models.organisation import Organisation
    from app.transport.models import OrganisationTransportProfile

    org = Organisation(
        org_id=f"org-dob-{uuid.uuid4().hex[:8]}",
        country="UG",
        legal_name="Test Transport Co",
    )
    db.session.add(org)
    db.session.commit()
    profile = OrganisationTransportProfile(
        organisation_id=org.id,
        registration_type="transport_company",
        insurance_verified=False,
    )
    db.session.add(profile)
    db.session.commit()
    return profile


# ====================================================================
# A. Guest DOB - accommodation guest registration route
# ====================================================================

class TestGuestDOBBoundary:

    def _post(self, client, booking_id, **fields):
        data = {
            "guest_name": "John Doe",
            "guest_email": "john@example.com",
            "guest_phone": "+256700000000",
            "relationship_type": "adult",
        }
        data.update(fields)
        return client.post(
            f"/accommodation/guest/booking/{booking_id}/register",
            data=data,
        )

    def _latest(self, booking_id, guest_name=None):
        from app.accommodation.models.guest_registration import GuestRegistration

        query = GuestRegistration.query.filter_by(booking_id=booking_id)
        if guest_name:
            query = query.filter_by(guest_name=guest_name)
        return query.order_by(GuestRegistration.id.desc()).first()

    def test_valid_yyyy_mm_dd(self, client, guest_user, confirmed_booking):
        """YYYY-MM-DD -> stored as a Python date (Date column)."""
        booking_id = int(confirmed_booking.id)
        _login(client, guest_user)
        resp = self._post(client, booking_id, date_of_birth="1990-06-15")
        assert resp.status_code in (200, 302)
        reg = self._latest(booking_id, "John Doe")
        assert reg is not None
        assert isinstance(reg.date_of_birth, date)
        assert reg.date_of_birth == date(1990, 6, 15)

    def test_valid_leap_year(self, client, guest_user, confirmed_booking):
        """Leap-day date accepted."""
        booking_id = int(confirmed_booking.id)
        _login(client, guest_user)
        resp = self._post(client, booking_id, date_of_birth="2024-02-29")
        assert resp.status_code in (200, 302)
        reg = self._latest(booking_id, "John Doe")
        assert reg.date_of_birth == date(2024, 2, 29)

    def test_whitespace_trimmed(self, client, guest_user, confirmed_booking):
        """Whitespace around the date is stripped before parsing."""
        booking_id = int(confirmed_booking.id)
        _login(client, guest_user)
        resp = self._post(client, booking_id, date_of_birth="  1995-03-20  ")
        assert resp.status_code in (200, 302)
        reg = self._latest(booking_id, "John Doe")
        assert reg.date_of_birth == date(1995, 3, 20)

    def test_empty_string_stores_none(self, client, guest_user, confirmed_booking):
        """Empty string -> None (preserves or-None semantic, no DB error)."""
        booking_id = int(confirmed_booking.id)
        _login(client, guest_user)
        resp = self._post(client, booking_id, date_of_birth="")
        assert resp.status_code in (200, 302)
        reg = self._latest(booking_id, "John Doe")
        assert reg.date_of_birth is None

    def test_missing_field_stores_none(self, client, guest_user, confirmed_booking):
        """Omitted field -> None."""
        booking_id = int(confirmed_booking.id)
        _login(client, guest_user)
        resp = client.post(
            f"/accommodation/guest/booking/{booking_id}/register",
            data={
                "guest_name": "No DOB Person",
                "relationship_type": "adult",
            },
        )
        assert resp.status_code in (200, 302)
        reg = self._latest(booking_id, "No DOB Person")
        assert reg.date_of_birth is None

    def test_invalid_format_dd_mm_yyyy_rejected(self, client, guest_user, confirmed_booking):
        """DD/MM/YYYY is not YYYY-MM-DD -> controlled rejection, no row created."""
        booking_id = int(confirmed_booking.id)
        _login(client, guest_user)
        resp = self._post(client, booking_id, date_of_birth="15/06/1990",
                          guest_name="Bad Date Person")
        assert resp.status_code in (302, 200)
        assert self._latest(booking_id, "Bad Date Person") is None

    def test_invalid_format_abc_rejected(self, client, guest_user, confirmed_booking):
        """Non-date string -> controlled rejection, no row created."""
        booking_id = int(confirmed_booking.id)
        _login(client, guest_user)
        resp = self._post(client, booking_id, date_of_birth="abc",
                          guest_name="ABC Person")
        assert resp.status_code in (302, 200)
        assert self._latest(booking_id, "ABC Person") is None

    def test_impossible_date_rejected(self, client, guest_user, confirmed_booking):
        """Feb 30 is not a real date -> controlled rejection, no row created."""
        booking_id = int(confirmed_booking.id)
        _login(client, guest_user)
        resp = self._post(client, booking_id, date_of_birth="1990-02-30",
                          guest_name="Impossible Person")
        assert resp.status_code in (302, 200)
        assert self._latest(booking_id, "Impossible Person") is None


# ====================================================================
# B. Incident occurred_at - /api/transport/incidents
# ====================================================================

class TestIncidentOccurredAtBoundary:

    def _payload(self, **overrides):
        base = {
            "incident_type": "vehicle_issue",
            "severity": "medium",
            "title": f"Test incident {uuid.uuid4().hex[:6]}",
            "description": "Test description for date boundary",
            "occurred_at": "2026-09-30T14:30:00+03:00",
            "reported_by": "Test Reporter",
            "reported_via": "web_form",
        }
        base.update(overrides)
        return base

    def _latest(self, title):
        from app.transport.models import TransportIncident

        return TransportIncident.query.filter_by(title=title).first()

    def test_tz_offset_normalized_to_utc(self, client, admin_user):
        """+03:00 at 14:30 -> stored instant == 11:30 UTC."""
        _login(client, admin_user)
        payload = self._payload(title="Offset incident",
                                occurred_at="2026-09-30T14:30:00+03:00")
        resp = client.post("/api/transport/incidents", json=payload,
                           content_type="application/json")
        assert resp.status_code == 201
        inc = self._latest(payload["title"])
        assert inc is not None
        assert inc.occurred_at.tzinfo is not None
        utc = _utc(inc.occurred_at)
        assert utc.utcoffset() == timedelta(0)
        assert utc.hour == 11
        assert utc.minute == 30

    def test_z_suffix_accepted(self, client, admin_user):
        """Z suffix accepted and treated as UTC."""
        _login(client, admin_user)
        payload = self._payload(title="Z-suffix incident",
                                occurred_at="2026-09-30T14:30:00Z")
        resp = client.post("/api/transport/incidents", json=payload,
                           content_type="application/json")
        assert resp.status_code == 201
        inc = self._latest(payload["title"])
        utc = _utc(inc.occurred_at)
        assert utc.utcoffset() == timedelta(0)
        assert utc.hour == 14
        assert utc.minute == 30

    def test_offset_and_z_same_instant(self, client, admin_user):
        """14:30+03:00 == 11:30Z -> identical stored instant."""
        _login(client, admin_user)
        p1 = self._payload(title="Offset-incident", occurred_at="2026-09-30T14:30:00+03:00")
        p2 = self._payload(title="Z-incident", occurred_at="2026-09-30T11:30:00Z")
        assert client.post("/api/transport/incidents", json=p1,
                           content_type="application/json").status_code == 201
        assert client.post("/api/transport/incidents", json=p2,
                           content_type="application/json").status_code == 201
        i1 = self._latest(p1["title"])
        i2 = self._latest(p2["title"])
        assert _utc(i1.occurred_at) == _utc(i2.occurred_at)

    def test_naive_rejected(self, client, admin_user):
        """Naive datetime (no offset) -> 400; DB session TZ must not decide."""
        _login(client, admin_user)
        payload = self._payload(title="Naive incident", occurred_at="2026-09-30T14:30:00")
        resp = client.post("/api/transport/incidents", json=payload,
                           content_type="application/json")
        assert resp.status_code == 400
        assert "timezone" in resp.json["error"].lower()
        assert self._latest(payload["title"]) is None

    def test_date_only_rejected(self, client, admin_user):
        """Date-only string -> 400 (no time or timezone)."""
        _login(client, admin_user)
        payload = self._payload(title="Date-only incident", occurred_at="2026-09-30")
        resp = client.post("/api/transport/incidents", json=payload,
                           content_type="application/json")
        assert resp.status_code == 400
        assert self._latest(payload["title"]) is None

    def test_empty_string_rejected(self, client, admin_user):
        """Empty string -> 400."""
        _login(client, admin_user)
        payload = self._payload(title="Empty incident", occurred_at="")
        resp = client.post("/api/transport/incidents", json=payload,
                           content_type="application/json")
        assert resp.status_code == 400

    def test_malformed_string_rejected(self, client, admin_user):
        """Non-ISO string -> 400."""
        _login(client, admin_user)
        payload = self._payload(title="Malformed incident", occurred_at="30/09/2026 14:30")
        resp = client.post("/api/transport/incidents", json=payload,
                           content_type="application/json")
        assert resp.status_code == 400
        assert self._latest(payload["title"]) is None

    def test_invalid_produces_no_row(self, client, admin_user):
        """Invalid occurred_at leaves incident count unchanged."""
        _login(client, admin_user)
        before = db.session.execute(
            db.text("SELECT COUNT(*) FROM transport_incidents")
        ).scalar()
        payload = self._payload(title="Should not exist", occurred_at="not-a-date")
        assert client.post("/api/transport/incidents", json=payload,
                           content_type="application/json").status_code == 400
        after = db.session.execute(
            db.text("SELECT COUNT(*) FROM transport_incidents")
        ).scalar()
        assert after == before


# ====================================================================
# C. Vehicle maintenance dates x4 - /api/transport/vehicles/<id>/maintenance
# ====================================================================

class TestVehicleMaintenanceDateBoundary:

    def _post(self, client, vehicle_id, **payload):
        return client.post(
            f"/api/transport/vehicles/{vehicle_id}/maintenance",
            json=payload or {},
            content_type="application/json",
        )

    def _vehicle(self, vehicle_id):
        from app.transport.models import Vehicle

        return db.session.get(Vehicle, vehicle_id)

    def test_next_service_date_yyyy_mm_dd(self, client, admin_user, test_vehicle):
        """YYYY-MM-DD -> tz-aware UTC midnight for next_service_date."""
        vehicle_id = int(test_vehicle.id)
        _login(client, admin_user)
        resp = self._post(client, vehicle_id,
                          event_type="service", next_service_date="2026-12-01")
        assert resp.status_code == 200
        v = self._vehicle(vehicle_id)
        assert v is not None and v.next_service_date is not None
        utc = _utc(v.next_service_date)
        assert utc.utcoffset() == timedelta(0)
        assert utc.year == 2026
        assert utc.month == 12
        assert utc.day == 1
        assert utc.hour == 0

    def test_next_inspection_due_date_only(self, client, admin_user, test_vehicle):
        """YYYY-MM-DD -> midnight UTC for next_inspection_due."""
        vehicle_id = int(test_vehicle.id)
        _login(client, admin_user)
        resp = self._post(client, vehicle_id,
                          event_type="inspection",
                          next_inspection_due="2026-11-15",
                          certificate_number="CERT-123")
        assert resp.status_code == 200
        v = self._vehicle(vehicle_id)
        assert v is not None and v.next_inspection_due is not None
        utc = _utc(v.next_inspection_due)
        assert utc.utcoffset() == timedelta(0)
        assert utc.hour == 0
        assert utc.day == 15

    def test_roadworthiness_expiry_with_z(self, client, admin_user, test_vehicle):
        """ISO datetime with Z accepted for roadworthiness_expiry."""
        vehicle_id = int(test_vehicle.id)
        _login(client, admin_user)
        resp = self._post(client, vehicle_id,
                          event_type="inspection",
                          roadworthiness_expiry="2027-06-30T12:00:00Z")
        assert resp.status_code == 200
        v = self._vehicle(vehicle_id)
        assert v is not None and v.roadworthiness_expiry is not None
        utc = _utc(v.roadworthiness_expiry)
        assert utc.utcoffset() == timedelta(0)
        assert utc.hour == 12

    def test_insurance_expiry_yyyy_mm_dd(self, client, admin_user, test_vehicle):
        """YYYY-MM-DD for insurance expiry (from 'expiry' key)."""
        vehicle_id = int(test_vehicle.id)
        _login(client, admin_user)
        resp = self._post(client, vehicle_id,
                          event_type="insurance",
                          expiry="2027-05-20",
                          provider="TestCo", policy_number="POL-1")
        assert resp.status_code == 200
        v = self._vehicle(vehicle_id)
        assert v is not None and v.insurance_expiry is not None
        utc = _utc(v.insurance_expiry)
        assert utc.utcoffset() == timedelta(0)
        assert utc.day == 20

    def test_empty_string_stores_none(self, client, admin_user, test_vehicle):
        """Empty string -> None for insurance expiry."""
        vehicle_id = int(test_vehicle.id)
        _login(client, admin_user)
        resp = self._post(client, vehicle_id,
                          event_type="insurance",
                          expiry="")
        assert resp.status_code == 200
        v = self._vehicle(vehicle_id)
        assert v.insurance_expiry is None

    def test_omitted_stores_none(self, client, admin_user, test_vehicle):
        """Omitting next_service_date entirely -> field stays None."""
        vehicle_id = int(test_vehicle.id)
        _login(client, admin_user)
        resp = self._post(client, vehicle_id, event_type="service")
        assert resp.status_code == 200
        v = self._vehicle(vehicle_id)
        assert v.next_service_date is None

    def test_next_service_date_malformed_rejected(self, client, admin_user, test_vehicle):
        """Non-parseable next_service_date -> controlled 400, no commit."""
        vehicle_id = int(test_vehicle.id)
        _login(client, admin_user)
        resp = self._post(client, vehicle_id,
                          event_type="service",
                          next_service_date="next monday")
        assert resp.status_code == 400
        assert "next_service_date" in resp.json["error"]
        v = self._vehicle(vehicle_id)
        assert v.next_service_date is None

    def test_inspection_malformed_rejected(self, client, admin_user, test_vehicle):
        """Non-parseable roadworthiness_expiry -> 400, no commit."""
        vehicle_id = int(test_vehicle.id)
        _login(client, admin_user)
        resp = self._post(client, vehicle_id,
                          event_type="inspection",
                          roadworthiness_expiry="end of time")
        assert resp.status_code == 400
        assert "roadworthiness_expiry" in resp.json["error"]

    def test_insurance_malformed_rejected(self, client, admin_user, test_vehicle):
        """Non-parseable expiry -> 400, no commit."""
        vehicle_id = int(test_vehicle.id)
        _login(client, admin_user)
        resp = self._post(client, vehicle_id,
                          event_type="insurance",
                          expiry="end of year")
        assert resp.status_code == 400
        assert "expiry" in resp.json["error"]


# ====================================================================
# D. Organisation insurance_expiry - /api/transport/organisations/<id>
# ====================================================================

class TestOrganisationInsuranceExpiryBoundary:

    def _put(self, client, org_id, **payload):
        return client.put(
            f"/api/transport/organisations/{org_id}",
            json=payload,
            content_type="application/json",
        )

    def _profile(self, org_id):
        from app.transport.models import OrganisationTransportProfile

        return db.session.get(OrganisationTransportProfile, org_id)

    def test_valid_yyyy_mm_dd(self, client, admin_user, test_organisation):
        """YYYY-MM-DD -> tz-aware UTC midnight."""
        org_id = int(test_organisation.id)
        _login(client, admin_user)
        resp = self._put(client, org_id,
                         insurance_verified=True,
                         insurance_expiry="2027-01-15")
        assert resp.status_code == 200
        o = self._profile(org_id)
        assert o is not None and o.insurance_expiry is not None
        utc = _utc(o.insurance_expiry)
        assert utc.utcoffset() == timedelta(0)
        assert utc.year == 2027
        assert utc.month == 1
        assert utc.day == 15
        assert utc.hour == 0

    def test_valid_z_suffix(self, client, admin_user, test_organisation):
        """Z-suffix ISO datetime accepted."""
        org_id = int(test_organisation.id)
        _login(client, admin_user)
        resp = self._put(client, org_id,
                         insurance_verified=True,
                         insurance_expiry="2027-06-15T10:00:00Z")
        assert resp.status_code == 200
        o = self._profile(org_id)
        assert o is not None
        utc = _utc(o.insurance_expiry)
        assert utc.utcoffset() == timedelta(0)
        assert utc.hour == 10

    def test_empty_string_stores_none(self, client, admin_user, test_organisation):
        """Empty string -> None."""
        org_id = int(test_organisation.id)
        _login(client, admin_user)
        resp = self._put(client, org_id,
                         insurance_verified=True,
                         insurance_expiry="")
        assert resp.status_code == 200
        o = self._profile(org_id)
        assert o.insurance_expiry is None

    def test_none_value_stores_none(self, client, admin_user, test_organisation):
        """Explicit JSON null -> None."""
        org_id = int(test_organisation.id)
        _login(client, admin_user)
        resp = self._put(client, org_id,
                         insurance_verified=True,
                         insurance_expiry=None)
        assert resp.status_code == 200
        o = self._profile(org_id)
        assert o.insurance_expiry is None

    def test_malformed_string_rejected(self, client, admin_user, test_organisation):
        """Non-parseable string -> 400, value unchanged."""
        org_id = int(test_organisation.id)
        _login(client, admin_user)
        resp = self._put(client, org_id,
                         insurance_verified=True,
                         insurance_expiry="next year")
        assert resp.status_code == 400
        assert "insurance_expiry" in resp.json["error"]

    def test_slash_format_rejected(self, client, admin_user, test_organisation):
        """DD/MM/YYYY is not valid ISO -> 400."""
        org_id = int(test_organisation.id)
        _login(client, admin_user)
        resp = self._put(client, org_id,
                         insurance_verified=True,
                         insurance_expiry="15/01/2027")
        assert resp.status_code == 400