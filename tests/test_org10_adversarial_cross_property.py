"""
ORG-10 closure: adversarial child-resource cross-property tests.

Authority model under test (accommodation module, org-scoped):
  * An organisation member with ``org.accommodation.manage`` (here an org_owner
    of Org A) may manage properties owned by THAT organisation (A, B).
  * The same actor must NOT manage properties of another organisation (C).
  * Child resources (room types, rooms, documents, bookings) must NEVER be
    authorized through a child ID alone. Routes derive the canonical parent
    property from the child FK, or enforce parent-ID binding.

Resolved behaviours locked by this file:
  * accommodation host routes authorize the derived parent property via
    AccommodationIdentityService.can_manage_property() — cross-org -> 403.
  * parent/child binding guards (e.g. booking.property_id != url property_id,
    room_type.property_id != url property_id) -> 404 / deny even within a
    same-org context.

Service-level matrix (Org A actor):
    Property A (Org A) -> True   (intentional, same org)
    Property B (Org A) -> True   (intentional, same org)
    Property C (Org B) -> False  (cross-org)

Run: pytest tests/test_org10_adversarial_cross_property.py -v
"""

import json
import uuid
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.accommodation.models.property import Property
from app.accommodation.models.property_document import (
    PropertyDocument,
    PropertyDocumentType,
)
from app.accommodation.models.room import Room, RoomType
from app.accommodation.services.host_service import HostService
from app.accommodation.services.identity_service import AccommodationIdentityService
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import (
    OrganisationMember,
    OrgRole,
    OrgUserRole,
)
from app.identity.models.organisation_provider_capability import (
    ProviderCapabilityCode,
    ProviderCapabilityStatus,
)
from app.identity.models.organization_types import OrganizationType
from app.identity.models.provider_participation import ProviderParticipation
from app.identity.models.roles_permission import get_or_create_role
from app.identity.models.user import User, UserRole
from app.profile.models import UserProfile


# ---------------------------------------------------------------------------
# Shared scenario builders (mirror stage4b6 helpers)
# ---------------------------------------------------------------------------

def _make_user(session, *, owner=False):
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"u_{uuid.uuid4().hex[:8]}",
        email=f"u_{uuid.uuid4().hex[:8]}@example.com",
    )
    user.set_password("TestPassword123!")
    user.is_active = True
    user.is_verified = True
    user.email_verified = True
    session.add(user)
    session.flush()

    role_name, level = ("owner", 1) if owner else ("user", 6)
    role = get_or_create_role(role_name, level=level)
    session.add(UserRole(user_id=user.id, role_id=role.id))
    session.add(
        UserProfile(
            user_id=user.public_id,
            full_name="Test User",
            profile_completed=owner,
        )
    )
    session.flush()
    return SimpleNamespace(
        id=user.id,
        public_id=user.public_id,
        username=user.username,
        email=user.email,
    )


def _make_org(session, *, org_type):
    org = Organisation(
        org_id=f"org_{uuid.uuid4().hex[:10]}",
        legal_name=f"Org {uuid.uuid4().hex[:8]}",
        country="UG",
        business_category=org_type,
        verification_status="verified",
        lifecycle_state="registered",
        is_active=True,
        is_operational=True,
    )
    session.add(org)
    session.flush()
    return org


def _assign_org_role(session, user, org, role_name):
    from app.identity.services.organisation_role_provisioning import (
        provision_organisation_roles,
    )

    provision_organisation_roles(org, commit=False)
    session.flush()

    membership = OrganisationMember(
        user_id=user.id,
        organisation_id=org.id,
        is_active=True,
    )
    session.add(membership)
    session.flush()

    org_role = OrgRole.query.filter_by(
        organisation_id=org.id,
        name=role_name,
    ).first()
    assert org_role is not None

    session.add(
        OrgUserRole(
            organisation_member_id=membership.id,
            role_id=org_role.id,
            assigned_by=user.id,
        )
    )
    session.flush()
    return membership


def _seed_org_pp(session, org_id, status):
    row = ProviderParticipation(
        user_id=None,
        organisation_id=org_id,
        capability_code=ProviderCapabilityCode.ACCOMMODATION.value,
        status=status,
    )
    session.add(row)
    session.flush()
    return row


def _property_data(suffix):
    return {
        "title": f"ORG-10 Suite {suffix}",
        "summary": "Cross-property adversarial test property",
        "description": "Used to prove child-resource authorization boundaries",
        "property_type": "hotel",
        "listing_type": "private_room",
        "address_line1": "Nakasero Hill Road",
        "address_line2": "",
        "city": "Kampala",
        "state": "",
        "country": "UG",
        "postal_code": "",
        "max_guests": 4,
        "bedrooms": 2,
        "beds": 3,
        "bathrooms": 2.0,
        "base_price_per_night": 150.00,
        "currency": "USD",
        "cleaning_fee": 30.00,
        "service_fee_pct": 10.00,
        "min_stay_nights": 1,
        "max_stay_nights": None,
        "cancellation_policy": "moderate",
        "check_in_time": "14:00",
        "check_out_time": "11:00",
        "instant_book": True,
        "allow_pets": False,
        "allow_smoking": False,
        "allow_events": False,
        "house_rules": None,
        "main_image": "",
        "gallery_urls": "",
        "meta_title": "",
        "meta_description": "",
    }


def _add_room_type(session, property_id, name):
    rt = RoomType(
        property_id=property_id,
        name=name,
        base_price_per_night=100.0,
        total_units=1,
        is_active=True,
    )
    session.add(rt)
    session.flush()
    return rt


def _add_room(session, property_id, room_type_id, room_number):
    room = Room(
        property_id=property_id,
        room_type_id=room_type_id,
        room_number=room_number,
        status="available",
        is_maintenance=False,
    )
    session.add(room)
    session.flush()
    return room


def _add_document(session, property_id):
    doc = PropertyDocument(
        property_id=property_id,
        document_type=PropertyDocumentType.ID_DOCUMENT,
        file_url="https://example.test/doc.jpg",
        file_name="id.jpg",
    )
    session.add(doc)
    session.flush()
    return doc


def _add_booking(session, property_id, actor_id):
    from app.accommodation.models.booking import AccommodationBooking

    booking = AccommodationBooking(
        booking_reference=f"BK-{uuid.uuid4().hex[:10]}",
        property_id=property_id,
        host_user_id=actor_id,
        booked_by_user_id=actor_id,
        check_in=date.today() + timedelta(days=14),
        check_out=date.today() + timedelta(days=16),
        num_nights=2,
        nightly_rate=Decimal("100.00"),
        total_amount=Decimal("200.00"),
    )
    session.add(booking)
    session.flush()
    return booking


def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.public_id)
        sess["_fresh"] = True


def _fake_org_host_identity(org_id):
    return {
        "type": "organisation",
        "id": org_id,
        "display_name": "Fake Test Org",
        "member_role": "admin",
    }


@pytest.fixture
def client(app):
    """Function-scoped client — avoids cross-test session leakage."""
    return app.test_client()


@pytest.fixture
def accommodation_module_on(app):
    """Temporarily enable the accommodation module for HTTP tests."""
    from app.models.system_config import SystemConfig
    from app.utils.module_toggle_service import ModuleToggleService

    with app.app_context():
        stored = SystemConfig.query.filter_by(key="MODULE_FLAGS").first()
        prev_null = stored is None or stored.value is None
        prev = ModuleToggleService._fetch_stored_flags()

        merged = dict(prev)
        merged["accommodation"] = True
        SystemConfig.set(
            "MODULE_FLAGS", json.dumps(merged), value_type="json",
            description="Module flags", commit=True,
        )
        ModuleToggleService.load_overrides_into_app()

    yield

    with app.app_context():
        if prev_null:
            row = SystemConfig.query.filter_by(key="MODULE_FLAGS").first()
            if row is not None:
                db.session.delete(row)
                db.session.commit()
        else:
            SystemConfig.set(
                "MODULE_FLAGS", json.dumps(prev), value_type="json",
                description="Module flags", commit=True,
            )
        ModuleToggleService.load_overrides_into_app()


# ---------------------------------------------------------------------------
# Authorized-scope scenario builder (Org A owns A+B, Org B owns C)
# ---------------------------------------------------------------------------

class Org10Scenario:
    """Builds the Org A actor + properties A/B (Org A) and C (Org B)."""

    @staticmethod
    def build(app):
        with app.app_context():
            actor = _make_user(db.session, owner=False)
            org_a = _make_org(db.session, org_type=OrganizationType.HOTEL)
            org_b = _make_org(db.session, org_type=OrganizationType.HOTEL)
            _assign_org_role(db.session, actor, org_a, "org_owner")
            _seed_org_pp(db.session, org_a.id, ProviderCapabilityStatus.ACTIVATED.value)
            _seed_org_pp(db.session, org_b.id, ProviderCapabilityStatus.ACTIVATED.value)
            db.session.flush()

            # Seed global accommodation permissions used by the org write gate.
            get_or_create_role("owner", level=1)
            get_or_create_role("admin", level=3)
            db.session.flush()

            prop_a = HostService.create_property(
                _property_data("PropA"), owner_user_id=None, owner_org_id=org_a.id,
            )
            prop_b = HostService.create_property(
                _property_data("PropB"), owner_user_id=None, owner_org_id=org_a.id,
            )
            prop_c = HostService.create_property(
                _property_data("PropC"), owner_user_id=None, owner_org_id=org_b.id,
            )
            db.session.flush()

            # Publish + open all three properties so the test targets the
            # authorization boundary rather than publication state.
            for prop in (prop_a, prop_b, prop_c):
                prop.status = "published"
                prop.is_verified = True
                prop.is_publicly_visible = True
                prop.is_active = True
                db.session.flush()

            rt_a = _add_room_type(db.session, prop_a.id, "Std A")
            rt_b = _add_room_type(db.session, prop_b.id, "Std B")
            rt_c = _add_room_type(db.session, prop_c.id, "Std C")

            room_a = _add_room(db.session, prop_a.id, rt_a.id, "A-101")
            room_b = _add_room(db.session, prop_b.id, rt_b.id, "B-101")
            room_c = _add_room(db.session, prop_c.id, rt_c.id, "C-101")

            doc_b = _add_document(db.session, prop_b.id)
            doc_c = _add_document(db.session, prop_c.id)

            booking_b = _add_booking(db.session, prop_b.id, actor.id)
            booking_c = _add_booking(db.session, prop_c.id, actor.id)

            db.session.commit()

            actor_out = SimpleNamespace(
                id=actor.id,
                public_id=actor.public_id,
                username=actor.username,
                email=actor.email,
            )
            return SimpleNamespace(
                actor=actor_out,
                org_a_id=org_a.id,
                org_b_id=org_b.id,
                prop_a_id=prop_a.id,
                prop_b_id=prop_b.id,
                prop_c_id=prop_c.id,
                prop_a_org_id=prop_a.owner_org_id,
                prop_b_org_id=prop_b.owner_org_id,
                prop_c_org_id=prop_c.owner_org_id,
                rt_a_id=rt_a.id,
                rt_b_id=rt_b.id,
                rt_c_id=rt_c.id,
                room_a_id=room_a.id,
                room_b_id=room_b.id,
                room_c_id=room_c.id,
                doc_b_id=doc_b.id,
                doc_c_id=doc_c.id,
                booking_b_id=booking_b.id,
                booking_c_id=booking_c.id,
            )


# ---------------------------------------------------------------------------
# 1. Service-level authority matrix (accommodation module)
# ---------------------------------------------------------------------------

class TestServiceLevelAuthorityMatrix:

    def test_can_manage_property_matrix(self, app):
        s = Org10Scenario.build(app)

        def _as_user():
            return db.session.get(User, s.actor.id)

        with app.app_context():
            user = _as_user()
            assert AccommodationIdentityService.can_manage_property(
                user, property_owner_org_id=s.prop_a_org_id,
            ) is True, "Org A actor must manage Property A (same org)"
            assert AccommodationIdentityService.can_manage_property(
                user, property_owner_org_id=s.prop_b_org_id,
            ) is True, "Org A actor must manage Property B (same org)"
            assert AccommodationIdentityService.can_manage_property(
                user, property_owner_org_id=s.prop_c_org_id,
            ) is False, "Org A actor must NOT manage Property C (cross org)"


# ---------------------------------------------------------------------------
# 2. RoomType child-resource substitution
# ---------------------------------------------------------------------------

class TestRoomTypeSubstitution:

    def test_cross_org_room_type_edit_denied(self, app, client, monkeypatch):
        s = Org10Scenario.build(app)
        _login(client, s.actor)
        monkeypatch.setattr(
            "app.accommodation.routes._ensure_host_identity",
            lambda: _fake_org_host_identity(s.org_a_id),
        )

        response = client.post(
            f"/accommodation/host/room-type/{s.rt_c_id}/edit",
            data={"name": "Hijacked", "base_price_per_night": "5"},
        )
        assert response.status_code == 403

        with app.app_context():
            rt = db.session.get(RoomType, s.rt_c_id)
            assert rt.name != "Hijacked", "cross-org room type must remain unchanged"

    def test_same_org_room_type_edit_allowed(self, app, client, monkeypatch):
        s = Org10Scenario.build(app)
        _login(client, s.actor)
        monkeypatch.setattr(
            "app.accommodation.routes._ensure_host_identity",
            lambda: _fake_org_host_identity(s.org_a_id),
        )

        response = client.post(
            f"/accommodation/host/room-type/{s.rt_b_id}/edit",
            data={"name": "Renamed B", "base_price_per_night": "120"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        with app.app_context():
            rt = db.session.get(RoomType, s.rt_b_id)
            assert rt.name == "Renamed B", "same-org room type edit should apply"

    def test_cross_property_room_type_binding_denied(self, app, client, monkeypatch):
        """room_type_id of Prop A used on Prop B's URL must be rejected even
        though both are in the same org — the operation is property-B-scoped."""
        s = Org10Scenario.build(app)
        _login(client, s.actor)
        monkeypatch.setattr(
            "app.accommodation.routes._ensure_host_identity",
            lambda: _fake_org_host_identity(s.org_a_id),
        )

        response = client.post(
            f"/accommodation/host/property/{s.prop_b_id}/rooms/add",
            data={"room_type_id": str(s.rt_a_id), "room_numbers": "77"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        with app.app_context():
            hijacked = Room.query.filter_by(property_id=s.prop_b_id, room_number="77").first()
            assert hijacked is None, "room must not be created under a foreign room type"

    def test_cross_org_room_add_denied(self, app, client, monkeypatch):
        s = Org10Scenario.build(app)
        _login(client, s.actor)
        monkeypatch.setattr(
            "app.accommodation.routes._ensure_host_identity",
            lambda: _fake_org_host_identity(s.org_a_id),
        )

        response = client.post(
            f"/accommodation/host/property/{s.prop_c_id}/rooms/add",
            data={"room_type_id": str(s.rt_c_id), "room_numbers": "1"},
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# 3. Room child-resource substitution
# ---------------------------------------------------------------------------

class TestRoomSubstitution:

    def test_cross_org_room_delete_denied(self, app, client, monkeypatch):
        s = Org10Scenario.build(app)
        _login(client, s.actor)
        monkeypatch.setattr(
            "app.accommodation.routes._ensure_host_identity",
            lambda: _fake_org_host_identity(s.org_a_id),
        )

        response = client.post(f"/accommodation/host/room/{s.room_c_id}/delete")
        assert response.status_code == 403

        with app.app_context():
            assert db.session.get(Room, s.room_c_id) is not None, "cross-org room must survive"

    def test_cross_org_room_maintenance_denied(self, app, client, monkeypatch):
        s = Org10Scenario.build(app)
        _login(client, s.actor)
        monkeypatch.setattr(
            "app.accommodation.routes._ensure_host_identity",
            lambda: _fake_org_host_identity(s.org_a_id),
        )

        response = client.post(
            f"/accommodation/host/room/{s.room_c_id}/maintenance",
            data={"maintenance_reason": "hijack"},
        )
        assert response.status_code == 403

        with app.app_context():
            room = db.session.get(Room, s.room_c_id)
            assert room.is_maintenance is False, "cross-org room state must remain unchanged"

    def test_same_org_room_delete_allowed(self, app, client, monkeypatch):
        s = Org10Scenario.build(app)
        _login(client, s.actor)
        monkeypatch.setattr(
            "app.accommodation.routes._ensure_host_identity",
            lambda: _fake_org_host_identity(s.org_a_id),
        )

        response = client.post(
            f"/accommodation/host/room/{s.room_b_id}/delete", follow_redirects=False,
        )
        assert response.status_code == 302

        with app.app_context():
            assert db.session.get(Room, s.room_b_id) is None, "same-org room should be deleted"


# ---------------------------------------------------------------------------
# 4. PropertyDocument child-resource substitution
# ---------------------------------------------------------------------------

class TestDocumentSubstitution:

    def test_cross_org_document_delete_denied(self, app, client, monkeypatch):
        s = Org10Scenario.build(app)
        _login(client, s.actor)
        monkeypatch.setattr(
            "app.accommodation.routes._ensure_host_identity",
            lambda: _fake_org_host_identity(s.org_a_id),
        )

        response = client.post(
            f"/accommodation/host/document/{s.doc_c_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/accommodation/host/dashboard")

        with app.app_context():
            assert db.session.get(PropertyDocument, s.doc_c_id) is not None, \
                "cross-org document must survive"

    def test_same_org_document_delete_allowed(self, app, client, monkeypatch):
        s = Org10Scenario.build(app)
        _login(client, s.actor)
        monkeypatch.setattr(
            "app.accommodation.routes._ensure_host_identity",
            lambda: _fake_org_host_identity(s.org_a_id),
        )

        response = client.post(
            f"/accommodation/host/document/{s.doc_b_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302

        with app.app_context():
            assert db.session.get(PropertyDocument, s.doc_b_id) is None, \
                "same-org pending document should be deleted"


# ---------------------------------------------------------------------------
# 5. Booking child-resource substitution
# ---------------------------------------------------------------------------

class TestBookingSubstitution:

    def test_cross_org_booking_via_cross_org_property_denied(self, app, client,
                                                             accommodation_module_on, monkeypatch):
        s = Org10Scenario.build(app)
        _login(client, s.actor)
        monkeypatch.setattr(
            "app.accommodation.routes._ensure_host_identity",
            lambda: _fake_org_host_identity(s.org_a_id),
        )

        response = client.post(
            f"/accommodation/host/property/{s.prop_c_id}/booking/{s.booking_c_id}/cancel",
            data={"reason": "hijack"},
        )
        assert response.status_code == 403

    def test_cross_org_booking_via_same_org_property_url_denied(self, app, client,
                                                                accommodation_module_on, monkeypatch):
        """Booking C (Org B) addressed through Property A's URL must 404 via the
        parent/child binding guard — the URL property is authorized but the
        booking does not belong to it."""
        s = Org10Scenario.build(app)
        _login(client, s.actor)
        monkeypatch.setattr(
            "app.accommodation.routes._ensure_host_identity",
            lambda: _fake_org_host_identity(s.org_a_id),
        )

        response = client.post(
            f"/accommodation/host/property/{s.prop_a_id}/booking/{s.booking_c_id}/cancel",
            data={"reason": "hijack"},
        )
        assert response.status_code == 404

    def test_same_org_booking_via_wrong_property_url_denied(self, app, client,
                                                            accommodation_module_on, monkeypatch):
        """Booking B (Org A) addressed through Property A's URL must still 404:
        within an org you may manage the booking only through the booking's own
        property context."""
        s = Org10Scenario.build(app)
        _login(client, s.actor)
        monkeypatch.setattr(
            "app.accommodation.routes._ensure_host_identity",
            lambda: _fake_org_host_identity(s.org_a_id),
        )

        response = client.post(
            f"/accommodation/host/property/{s.prop_a_id}/booking/{s.booking_b_id}/cancel",
            data={"reason": "hijack"},
        )
        assert response.status_code == 404

    def test_same_org_booking_via_own_property_allowed(self, app, client,
                                                       accommodation_module_on, monkeypatch):
        s = Org10Scenario.build(app)
        _login(client, s.actor)
        monkeypatch.setattr(
            "app.accommodation.routes._ensure_host_identity",
            lambda: _fake_org_host_identity(s.org_a_id),
        )

        response = client.post(
            f"/accommodation/host/property/{s.prop_b_id}/booking/{s.booking_b_id}/cancel",
            data={"reason": "organization change"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert f"/accommodation/host/property/{s.prop_b_id}" in response.headers["Location"]