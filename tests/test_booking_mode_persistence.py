"""Focused regression tests: HostService must persist Property.booking_mode.

Verified defect (2026-09-08): ``host_service.create_property`` and
``host_service.update_property`` wrote ``instant_book`` but never persisted the
canonical ``Property.booking_mode`` column (``String(20), default="instant"``).
A host selecting ``host_approval`` had the value silently dropped, so
``booking_service`` (which routes on ``property.booking_mode == 'host_approval'``)
never entered the host-approval flow.

These tests prove the create/update paths persist the selected booking_mode and
the default is ``"instant"`` when omitted.
"""
import uuid
from decimal import Decimal

from app.accommodation.models.property import Property
from app.accommodation.services.host_service import HostService
from app.extensions import db


def _host_user():
    from app.identity.models.user import User

    user = User(
        email=f"bm-host-{uuid.uuid4().hex[:6]}@example.com",
        username=f"bm-host-{uuid.uuid4().hex[:6]}",
        password_hash="not-a-real-hash",
        email_verified=True,
        phone_verified=True,
        kyc_level=2,
    )
    db.session.add(user)
    db.session.flush()
    return user


def _property_data():
    return {
        "title": f"Booking Mode Test {uuid.uuid4().hex[:8]}",
        "summary": "Persistence regression test property",
        "description": "Proves booking_mode persistence through the host flow",
        "property_type": "house",
        "listing_type": "entire_place",
        "address_line1": "Test Host Road",
        "address_line2": "",
        "city": "Kampala",
        "state": "",
        "country": "UG",
        "postal_code": "",
        "max_guests": 4,
        "bedrooms": 2,
        "beds": 2,
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
        "instant_book": False,
        "allow_pets": False,
        "allow_smoking": False,
        "allow_events": False,
        "house_rules": None,
        "main_image": "",
        "gallery_urls": "",
        "meta_title": "",
        "meta_description": "",
    }


def test_create_persists_host_approval_booking_mode(test_db):
    """Valid booking_mode on creation is persisted exactly."""
    owner = _host_user()
    data = _property_data()
    data["booking_mode"] = "host_approval"
    prop = HostService.create_property(data, owner_user_id=owner.id, owner_org_id=None)
    db.session.commit()
    prop_id = prop.id
    db.session.expire_all()
    stored = db.session.get(Property, prop_id)
    assert stored.booking_mode == "host_approval"


def test_create_persists_instant_booking_mode(test_db):
    """Explicit 'instant' booking_mode on creation is persisted."""
    owner = _host_user()
    data = _property_data()
    data["booking_mode"] = "instant"
    prop = HostService.create_property(data, owner_user_id=owner.id, owner_org_id=None)
    db.session.commit()
    prop_id = prop.id
    db.session.expire_all()
    stored = db.session.get(Property, prop_id)
    assert stored.booking_mode == "instant"


def test_create_defaults_to_instant_when_omitted(test_db):
    """Omitted booking_mode defaults to 'instant' (matches model default)."""
    owner = _host_user()
    data = _property_data()
    prop = HostService.create_property(data, owner_user_id=owner.id, owner_org_id=None)
    db.session.commit()
    prop_id = prop.id
    db.session.expire_all()
    stored = db.session.get(Property, prop_id)
    assert stored.booking_mode == "instant"


def test_update_persists_booking_mode_change(test_db):
    """Changing booking_mode via update_property is persisted (instant -> host_approval)."""
    owner = _host_user()
    data = _property_data()  # no booking_mode -> defaults to instant
    prop = HostService.create_property(data, owner_user_id=owner.id, owner_org_id=None)
    db.session.flush()

    update_data = _property_data()
    update_data["title"] = prop.title
    update_data["booking_mode"] = "host_approval"
    HostService.update_property(prop, update_data)
    db.session.commit()
    prop_id = prop.id
    db.session.expire_all()
    stored = db.session.get(Property, prop_id)
    assert stored.booking_mode == "host_approval"


def test_update_keeps_existing_mode_when_omitted(test_db):
    """Omitted booking_mode on update keeps the existing persisted value."""
    owner = _host_user()
    data = _property_data()
    data["booking_mode"] = "host_approval"
    prop = HostService.create_property(data, owner_user_id=owner.id, owner_org_id=None)
    db.session.flush()

    update_data = _property_data()
    update_data["title"] = prop.title  # no booking_mode key
    HostService.update_property(prop, update_data)
    db.session.commit()
    prop_id = prop.id
    db.session.expire_all()
    stored = db.session.get(Property, prop_id)
    assert stored.booking_mode == "host_approval"
