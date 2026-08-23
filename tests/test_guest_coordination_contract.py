"""Focused, database-free contract tests for Event guest coordination."""

from types import SimpleNamespace

import pytest
from flask import Flask

import app.events.guest_coordination_service as coordination
from app.notifications.events.policy import policy_engine
from app.notifications.events.registry import EventType, event_registry


class _Field:
    def __ne__(self, other):
        return True


class _Query:
    def __init__(self, count=0, item=None):
        self.count_value = count
        self.item = item

    def filter_by(self, **kwargs):
        return self

    def filter(self, *args):
        return self

    def count(self):
        return self.count_value

    def first(self):
        return self.item


class _Session:
    def __init__(self):
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1


class _DB:
    def __init__(self):
        self.session = _Session()


def _event():
    return SimpleNamespace(id=10, public_id="event-public", slug="event-slug")


def _registration(status="confirmed"):
    return SimpleNamespace(
        id=20,
        user_id=30,
        attendee_user_id=None,
        registration_ref="ER-EVENT-00000001",
        status=status,
        full_name="Guest One",
        email="guest@example.com",
        phone=None,
    )


def test_registration_requires_confirmed_status(monkeypatch):
    registration = _registration("pending")
    monkeypatch.setattr(
        coordination.EventRegistration,
        "query",
        _Query(item=registration),
    )

    with pytest.raises(coordination.CoordinationError) as error:
        coordination.GuestCoordinationService._registration(_event(), registration.registration_ref)

    assert error.value.code == "REGISTRATION_NOT_CONFIRMED"


def test_assignment_reference_is_public_and_stable():
    reference = coordination.GuestCoordinationService._assignment_ref(_event(), _registration())
    assert reference == "event-public:ER-EVENT-00000001"
    assert "10" not in reference
    assert "30" not in reference


def test_guest_reference_is_preferred_when_registration_is_linked():
    registration = _registration()
    registration.guest = SimpleNamespace(guest_ref="EG-public-1")
    reference = coordination.GuestCoordinationService._assignment_ref(_event(), registration)
    assert reference == "event-public:EG-public-1"
    assert "20" not in reference


def test_accommodation_assignment_passes_booking_reference_and_emits_no_internal_ref(monkeypatch):
    registration = _registration()
    assignment = SimpleNamespace(
        registration=registration,
        registration_id=registration.id,
        accommodation_booking_id=None,
        transport_booking_id=None,
        status="active",
    )
    booking = SimpleNamespace(id=99, booking_reference="ACC-PUBLIC-1", num_guests=1)
    fake_assignment_model = SimpleNamespace(
        query=_Query(count=0),
        registration_id=_Field(),
    )
    fake_db = _DB()
    committed = {}
    monkeypatch.setattr(coordination, "EventAssignment", fake_assignment_model)
    monkeypatch.setattr(coordination, "db", fake_db)
    monkeypatch.setattr(coordination.GuestCoordinationService, "_require", lambda *args: None)
    monkeypatch.setattr(coordination.GuestCoordinationService, "_registration", lambda *args: registration)
    monkeypatch.setattr(coordination.GuestCoordinationService, "_assignment", lambda *args: assignment)
    monkeypatch.setattr(coordination.GuestCoordinationService, "_resolve_accommodation_booking", lambda *args: booking)
    monkeypatch.setattr(
        coordination.GuestCoordinationService,
        "_commit_assignment",
        lambda *args: (committed.setdefault("args", args), assignment)[1],
    )

    result = coordination.GuestCoordinationService.assign_accommodation(
        _event(), SimpleNamespace(id=7, public_id="host-public"), registration.registration_ref, booking.booking_reference
    )

    assert result is assignment
    assert committed["args"][5] == "ACC-PUBLIC-1"
    assert 99 not in committed["args"]


def test_module_disable_returns_controlled_failure(monkeypatch):
    app = Flask(__name__)
    app.config["MODULE_FLAGS"] = {"accommodation": False}
    with app.app_context():
        monkeypatch.setattr(coordination.GuestCoordinationService, "_require", lambda *args: None)
        with pytest.raises(coordination.CoordinationError) as error:
            coordination.GuestCoordinationService.assign_accommodation(
                _event(), SimpleNamespace(id=7), "ER-EVENT-00000001", "ACC-PUBLIC-1"
            )
    assert error.value.code == "ACCOMMODATION_UNAVAILABLE"


def test_coordination_events_are_registered_and_notified():
    for event_type in (
        EventType.EVENT_ACCOMMODATION_ASSIGNED,
        EventType.EVENT_ACCOMMODATION_CHANGED,
        EventType.EVENT_TRANSPORT_ASSIGNED,
        EventType.EVENT_TRANSPORT_CHANGED,
        EventType.EVENT_COORDINATION_CANCELLED,
    ):
        assert event_registry.get(event_type) is not None
        assert policy_engine.policies_for(event_type)