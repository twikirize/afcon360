"""
ORG-9 closure: guest-facing public boundaries for the accommodation module.

Two previously-open guest-facing boundaries are now closed:

  * guest detail  -> GET /accommodation/guest/<identifier>
  * availability  -> GET /accommodation/api/availability

Only a property that passes the canonical public/booking boundary configured
for the public architecture may be served to guests. This test file locks the
boundary with live HTTP tests:

  * guest detail  - status 200 ONLY when the property is
    (active|published) + verified + publicly visible + active + not deleted
    + at least one active room type (mirrors public search). Every other
    shape of the same property is hidden (404).
  * availability  - status 200 ONLY when the property passes
    can_be_booked() AND is_publicly_visible. Non-bookable/publicly hidden
    properties and unknown ids are rejected (404).

Run: pytest tests/test_org9_public_boundaries.py -v
"""

import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.accommodation.models.property import Property
from app.accommodation.models.room import RoomType
from app.accommodation.services.availability_service import AvailabilityService
from app.identity.models.user import User


# ---------------------------------------------------------------------------
# Property factory
# ---------------------------------------------------------------------------

def _make_property(session, *, with_room_type=True, with_active_room_type=True,
                   soft_deleted=False, **overrides):
    """Create + commit a Property row with the requested visibility shape."""
    params = dict(
        slug=f"org9-{uuid.uuid4().hex[:10]}",
        title=f"ORG9 {uuid.uuid4().hex[:8]}",
        description="ORG-9 public boundary test property",
        address_line1="Test Road",
        city="Kampala",
        country="UG",
        base_price_per_night=120.0,
        property_type="house",
        listing_type="entire_place",
        status="active",
        is_verified=True,
        verification_status="verified",
        is_publicly_visible=True,
        is_active=True,
    )
    params.update(overrides)

    # ck_property_has_owner requires at least one owner reference.
    if not params.get("owner_user_id") and not params.get("owner_org_id"):
        owner = User(
            public_id=str(uuid.uuid4()),
            username=f"o_{uuid.uuid4().hex[:8]}",
            email=f"o_{uuid.uuid4().hex[:8]}@example.com",
        )
        owner.set_password("TestPassword123!")
        owner.is_active = True
        owner.is_verified = True
        owner.email_verified = True
        session.add(owner)
        session.flush()
        params["owner_user_id"] = owner.id

    prop = Property(**params)
    if soft_deleted:
        prop.soft_delete()
    session.add(prop)
    session.flush()

    if with_room_type:
        session.add(
            RoomType(
                property_id=prop.id,
                name="Standard",
                base_price_per_night=100.0,
                total_units=1,
                is_active=with_active_room_type,
            )
        )
        session.flush()

    session.commit()
    return SimpleNamespace(id=prop.id, public_id=prop.public_id)


def _guest_url(prop):
    return f"/accommodation/guest/{prop.public_id}"


def _availability_url(prop):
    check_in = (date.today() + timedelta(days=7)).isoformat()
    check_out = (date.today() + timedelta(days=9)).isoformat()
    return (
        f"/accommodation/api/availability?property_id={prop.id}"
        f"&check_in={check_in}&check_out={check_out}&num_guests=2&num_rooms=1"
    )


GUEST_DETAIL_BLOCKED_CASES = [
    ("draft", {"status": "draft"}),
    ("archived", {"status": "archived"}),
    ("suspended", {"status": "suspended"}),
    ("rejected", {"verification_status": "rejected", "is_verified": False}),
    ("unverified", {"verification_status": "unverified", "is_verified": False}),
    ("not_publicly_visible", {"is_publicly_visible": False}),
    ("inactive", {"is_active": False}),
    ("soft_deleted", {"soft_deleted": True}),
    ("no_room_type", {"with_room_type": False}),
    ("inactive_room_type", {"with_active_room_type": False}),
]

AVAILABILITY_BLOCKED_CASES = [
    ("draft", {"status": "draft"}),
    ("archived", {"status": "archived"}),
    ("suspended", {"status": "suspended"}),
    ("rejected", {"verification_status": "rejected", "is_verified": False}),
    ("unverified", {"verification_status": "unverified", "is_verified": False}),
    ("not_publicly_visible", {"is_publicly_visible": False}),
    ("inactive", {"is_active": False}),
    ("soft_deleted", {"soft_deleted": True}),
]


@pytest.fixture
def client(app):
    """Function-scoped client — avoids cross-test session leakage."""
    return app.test_client()


# ---------------------------------------------------------------------------
# Guest detail boundary
# ---------------------------------------------------------------------------

class TestGuestDetailPublicBoundary:

    @pytest.mark.parametrize("label,kwargs", GUEST_DETAIL_BLOCKED_CASES)
    def test_blocked_states_are_hidden(self, app, client, label, kwargs):
        with app.app_context():
            prop = _make_property(db.session, **kwargs)
        response = client.get(_guest_url(prop))
        assert response.status_code == 404, f"Expected 404 for guest detail case '{label}'"

    def test_fully_public_property_is_viewable(self, app, client):
        with app.app_context():
            prop = _make_property(db.session, status="published")
        response = client.get(_guest_url(prop))
        assert response.status_code == 200

    def test_active_public_verified_property_is_viewable(self, app, client):
        with app.app_context():
            prop = _make_property(db.session, status="active")
        response = client.get(_guest_url(prop))
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Availability boundary
# ---------------------------------------------------------------------------

class TestAvailabilityPublicBoundary:

    @pytest.mark.parametrize("label,kwargs", AVAILABILITY_BLOCKED_CASES)
    def test_blocked_states_are_rejected(self, app, client, label, kwargs):
        with app.app_context():
            prop = _make_property(db.session, **kwargs)
        response = client.get(_availability_url(prop))
        assert response.status_code == 404, f"Expected 404 for availability case '{label}'"
        data = response.get_json()
        assert data is not None and data.get("success") is False

    def test_unknown_property_id_is_rejected(self, client):
        response = client.get(_availability_url_unknown_id())
        assert response.status_code == 404
        data = response.get_json()
        assert data is not None and data.get("success") is False

    def test_public_bookable_property_is_served(self, app, client, monkeypatch):
        with app.app_context():
            prop = _make_property(db.session, status="published")

        def _fake_cascade(property_id=None, check_in=None, check_out=None,
                          num_guests=2, num_rooms=1, exclude_booking_id=None):
            return {
                "property_id": property_id,
                "room_types": [],
                "alternatives": [],
            }

        monkeypatch.setattr(
            AvailabilityService, "get_availability_cascade",
            staticmethod(_fake_cascade),
        )

        response = client.get(_availability_url(prop))
        assert response.status_code == 200
        data = response.get_json()
        assert data is not None and data.get("success") is True


def _availability_url_unknown_id():
    check_in = (date.today() + timedelta(days=7)).isoformat()
    check_out = (date.today() + timedelta(days=9)).isoformat()
    return (
        f"/accommodation/api/availability?property_id=99999999"
        f"&check_in={check_in}&check_out={check_out}&num_guests=2&num_rooms=1"
    )