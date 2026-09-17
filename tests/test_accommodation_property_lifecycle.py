import uuid

import pytest

from app.extensions import db
from app.accommodation.models.property import Property
from app.accommodation.models.room import RoomType
from app.accommodation.services.host_service import HostService
from app.accommodation.services.moderation_service import ModerationService
from app.accommodation.services.readiness_service import AccommodationReadinessService
from app.identity.models.user import User


@pytest.fixture(autouse=True)
def setup_postgres(app):
    with app.app_context():
        db.session.begin_nested()
        yield
        db.session.rollback()
        db.session.remove()


def _make_users():
    host = User.query.filter_by(email="lifecycle_host@example.com").first()
    if not host:
        host = User(
            username=f"lchost_{uuid.uuid4().hex[:8]}",
            email="lifecycle_host@example.com",
            is_verified=True,
            is_active=True,
        )
        host.set_password("Password123!")
        db.session.add(host)
        db.session.commit()

    mod = User.query.filter_by(email="lifecycle_mod@example.com").first()
    if not mod:
        mod = User(
            username=f"lcmod_{uuid.uuid4().hex[:8]}",
            email="lifecycle_mod@example.com",
            is_verified=True,
            is_active=True,
        )
        mod.set_password("Password123!")
        db.session.add(mod)
        db.session.commit()

    return host, mod


def _property_data(title):
    return {
        "title": title,
        "summary": "Lifecycle acceptance property",
        "description": "Approval is independent of inventory; publication requires inventory readiness.",
        "property_type": "hotel",
        "listing_type": "private_room",
        "address_line1": "Lifecycle Hill Road",
        "city": "Kampala",
        "country": "UG",
        "max_guests": 4,
        "bedrooms": 2,
        "beds": 2,
        "bathrooms": 2.0,
        "base_price_per_night": 150.00,
        "currency": "USD",
        "cleaning_fee": 30.00,
        "service_fee_pct": 10.00,
        "cancellation_policy": "moderate",
        "min_stay_nights": 1,
        "instant_book": True,
        "main_image": "https://example.com/main.jpg",
    }


def _add_room_type(prop, *, total_units=1, is_active=True, max_guests=None, base_price=None):
    rt = RoomType(
        property_id=prop.id,
        name=f"Room {uuid.uuid4().hex[:6]}",
        description="Room type",
        max_guests=max_guests if max_guests is not None else prop.max_guests,
        bedrooms=1,
        beds=1,
        bathrooms=1.0,
        base_price_per_night=base_price if base_price is not None else prop.base_price_per_night,
        currency=prop.currency,
        cleaning_fee=prop.cleaning_fee,
        service_fee_pct=prop.service_fee_pct,
        total_units=total_units,
        is_active=is_active,
    )
    db.session.add(rt)
    db.session.commit()
    return rt


def test_create_property_never_manufactures_inventory(app):
    with app.app_context():
        host, _ = _make_users()
        prop = HostService.create_property(_property_data("Lifecycle Create"), owner_user_id=host.id, owner_org_id=None)
        db.session.commit()

        assert prop.status == "pending_review"
        assert prop.is_active is False
        assert prop.room_types == []


def test_approval_succeeds_with_zero_inventory(app):
    """APPROVE → APPROVED even when inventory is NONE. Not published. Not bookable."""
    with app.app_context():
        host, mod = _make_users()
        prop = HostService.create_property(_property_data("Lifecycle Approve"), owner_user_id=host.id, owner_org_id=None)
        db.session.commit()

        ok, err = ModerationService.approve_property(prop.id, mod.id)
        assert ok is True
        assert err is None

        db.session.refresh(prop)
        assert prop.status == "approved"
        assert prop.is_verified is True
        assert prop.room_types == []
        assert prop.status != "published"
        assert prop.can_be_booked() is False
        assert prop.is_publicly_viewable() is False


def test_publish_with_zero_inventory_is_rejected(app):
    """PUBLISH → inventory readiness check blocks a property with no room types."""
    with app.app_context():
        host, mod = _make_users()
        prop = HostService.create_property(_property_data("Lifecycle PublishZero"), owner_user_id=host.id, owner_org_id=None)
        db.session.commit()
        ModerationService.approve_property(prop.id, mod.id)
        db.session.refresh(prop)
        assert prop.status == "approved"

        ok, err = ModerationService.publish_property(prop.id, mod.id)
        assert ok is False
        assert err and "room type" in err.lower()

        db.session.refresh(prop)
        assert prop.status == "approved"
        assert prop.is_active is False


def test_publish_with_incomplete_inventory_is_rejected(app):
    """A room-type row alone is NOT enough; each active room type must be fully configured."""
    with app.app_context():
        host, mod = _make_users()
        prop = HostService.create_property(_property_data("Lifecycle PublishIncomplete"), owner_user_id=host.id, owner_org_id=None)
        db.session.commit()
        ModerationService.approve_property(prop.id, mod.id)

        _add_room_type(prop, total_units=0, is_active=True)

        ok, err = ModerationService.publish_property(prop.id, mod.id)
        assert ok is False
        assert err and "at least 1 unit" in err.lower()

        db.session.refresh(prop)
        assert prop.status == "approved"


def test_publish_succeeds_with_one_fully_configured_active_room_type(app):
    """One fully configured, active, sellable RoomType → PUBLISH succeeds."""
    with app.app_context():
        host, mod = _make_users()
        prop = HostService.create_property(_property_data("Lifecycle PublishOk"), owner_user_id=host.id, owner_org_id=None)
        db.session.commit()
        ModerationService.approve_property(prop.id, mod.id)

        _add_room_type(prop, total_units=5, is_active=True)

        ok, err = ModerationService.publish_property(prop.id, mod.id)
        assert ok is True, err

        db.session.refresh(prop)
        assert prop.status == "published"
        assert prop.is_active is True
        assert prop.is_publicly_visible is True
        assert prop.can_be_booked() is True
        assert prop.is_publicly_viewable() is True


def test_publish_succeeds_with_inactive_or_invalid_room_types_plus_valid_active(app):
    """An inactive (even defective) room type plus one valid active room type → PUBLISH succeeds."""
    with app.app_context():
        host, mod = _make_users()
        prop = HostService.create_property(_property_data("Lifecycle PublishMulti"), owner_user_id=host.id, owner_org_id=None)
        db.session.commit()
        ModerationService.approve_property(prop.id, mod.id)

        _add_room_type(prop, total_units=0, is_active=False)
        _add_room_type(prop, total_units=3, is_active=True)

        ok, err = ModerationService.publish_property(prop.id, mod.id)
        assert ok is True, err

        db.session.refresh(prop)
        assert prop.status == "published"
        assert prop.is_publicly_viewable() is True


def test_public_boundary_approved_no_inventory_vs_published_valid_inventory(app):
    """Public boundary: approved + no inventory is NOT bookable/visible; published + valid inventory IS."""
    with app.app_context():
        host, mod = _make_users()
        prop = HostService.create_property(_property_data("Lifecycle Boundary"), owner_user_id=host.id, owner_org_id=None)
        db.session.commit()
        ModerationService.approve_property(prop.id, mod.id)
        db.session.refresh(prop)

        assert prop.can_be_booked() is False
        assert prop.is_publicly_viewable() is False

        _add_room_type(prop, total_units=2, is_active=True)
        ModerationService.publish_property(prop.id, mod.id)
        db.session.refresh(prop)

        assert prop.can_be_booked() is True
        assert prop.is_publicly_viewable() is True


def test_readiness_reason_for_zero_inventory_is_explicit(app):
    """The canonical readiness predicate returns a specific, actionable reason."""
    with app.app_context():
        host, _ = _make_users()
        prop = HostService.create_property(_property_data("Lifecycle Readiness"), owner_user_id=host.id, owner_org_id=None)
        db.session.commit()

        can_book, failures = AccommodationReadinessService.check_readiness(prop)
        assert can_book is False
        assert any("At least one active room type is required." in f for f in failures)