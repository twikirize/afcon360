"""Shadow-mode proof for the transport BookingSchema rollout gate.

Bounded scope (Phase A schema-adoption follow-up):
  * Prove ``BookingSchema`` executes on every booking request while
    ``TRANSPORT_BOOKING_SCHEMA_ENFORCE`` is False (the everywhere default).
  * Prove schema discrepancies are observable (logged / raisable) while the
    original form data and the booking behaviour remain unchanged.
  * Prove non-rejection when enforcement is disabled.
  * Prove the schema gate rejects before the service when enforcement is on
    (test-local flag override only).
  * Pin ``_SOURCE_KEYS`` to the canonical ``VALID_SOURCES`` contract so the
    two can never silently drift.

Nothing here activates enforcement in the codebase, changes booking policy,
or touches models/migrations. The service validator
(``app/utils/validators.py``) stays the enforced path.
"""
import logging
import uuid
from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest

from app.schemas.common import ValidationError as SchemaValidationError
from app.schemas.transport import BookingSchema, _SOURCE_KEYS


# The actual rider form contract (templates/transport/new_home.html): every
# value arrives as a string. `luggage_count` is the one field where the schema
# is deliberately stricter than the service (0..1000); everything else passes
# both, so it is the clean discrepancy probe.
def _form(**over):
    data = {
        "pickup_location": "Nile Stadium, Kampala",
        "dropoff_location": "Entebbe Airport",
        "pickup_latitude": "0.3150",
        "pickup_longitude": "32.5820",
        "dropoff_latitude": "0.3350",
        "dropoff_longitude": "32.6000",
        "pickup_time": "2099-12-31T10:00:00",
        "service_type": "on_demand",
        "provider_type": "individual_driver",
        "currency": "USD",
        "vehicle_class": "comfort",
        "payment_method": "cash",
        "passenger_count": "1",
        "luggage_count": "0",
    }
    data.update(over)
    return data


@pytest.fixture(scope="function")
def rider_with_kyc(app):
    """Rider with KYC tier >= 2 and a completed profile (booking gates)."""
    with app.app_context():
        from app.auth.kyc_compliance import calculate_kyc_tier
        from app.extensions import db
        from app.identity.individuals.individual_verification import (
            IndividualVerification,
        )
        from app.identity.models.roles_permission import get_or_create_role
        from app.identity.models.user import User, UserRole
        from app.profile.models import UserProfile

        user = User(
            public_id=str(uuid.uuid4()),
            username=f"shdw_{uuid.uuid4().hex[:8]}",
            email=f"shdw_{uuid.uuid4().hex[:8]}@test.example.com",
            phone=f"+2567{uuid.uuid4().hex[:7]}",
        )
        user.set_password("TestPass123!")
        user.is_active = True
        user.is_verified = True
        user.email_verified = True
        user.phone_verified = True
        user.phone_verified_at = datetime.now(timezone.utc)
        db.session.add(user)
        db.session.flush()

        role = get_or_create_role("user", level=6)
        db.session.add(UserRole(user_id=user.id, role_id=role.id))

        db.session.add(UserProfile(
            user_id=user.public_id,
            full_name="Schema Shadow Rider",
            date_of_birth=date(1995, 4, 12),
            nationality="UG",
            id_type="national_id",
            id_number=f"NID-SHDW-{uuid.uuid4().hex[:8].upper()}",
            profile_completed=True,
            verification_status="verified",
        ))
        db.session.flush()
        db.session.add(IndividualVerification(
            user_id=user.id, status="verified",
            scope={"national_id": True, "biometric": True},
        ))
        db.session.commit()

        assert calculate_kyc_tier(user.id)["tier"] >= 2
        return str(user.public_id)


def _login(client, public_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = public_id
        sess["_fresh"] = True


class _ListHandler(logging.Handler):
    """Capture records directly from the route logger.

    Two independent causes make a root-level capture (e.g. ``caplog``) miss
    these records:

    1. ``app.*`` loggers set ``propagate = False`` (``app/__init__.py``), so
       records never reach a root handler.
    2. ``migrations/env.py`` calls ``logging.config.fileConfig(...)``, whose
       ``disable_existing_loggers`` default (``True``) silently disables every
       pre-existing ``app.*`` logger for the pytest session.

    The test therefore re-enables the target logger and captures on it
    directly.
    """

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def patched_booking():
    """Patch booking side-effects so the route reaches the flash/redirect.

    Captures the exact dict handed to ``create_booking`` so the test can
    prove the raw form data (not schema-coerced output) is what the service
    receives.
    """
    from app.transport.services import booking_service as bs
    from app.transport.services import matching_service as ms

    calls = {"create": []}

    def mock_create(self, customer_id, booking_data, *a, **k):
        calls["create"].append(booking_data)
        return {"success": True, "data": {
            "booking_id": 999999, "booking_reference": "SHADOW123"}}

    with patch.object(bs.BookingService, "create_booking", mock_create), \
         patch.object(bs.BookingService, "transition_status",
                      lambda *a, **k: {"success": True}), \
         patch.object(ms.MatchingService, "discover_and_offer",
                      lambda *a, **k: {"offers_created": 0}):
        yield calls


# --- schema unit behavior ---------------------------------------------------

def test_load_returns_original_form_strings():
    """load() validates but returns the original strings (no coercion)."""
    form = _form()
    out = BookingSchema().load(form)
    assert out == form
    assert all(isinstance(out[k], str)
               for k in ("passenger_count", "luggage_count", "pickup_latitude"))


def test_schema_is_stricter_than_service_for_luggage_count():
    """The schema adds a 0..1000 bound the service does not enforce."""
    form = _form(luggage_count="5000")
    with pytest.raises(SchemaValidationError) as excinfo:
        BookingSchema().load(form)
    assert "luggage_count" in excinfo.value.messages

    from app.utils.validators import TransportValidators
    ok, errors = TransportValidators.validate_booking_request(form)
    assert ok is True, errors  # service accepts what the schema rejects


def test_source_keys_match_canonical_contract():
    """Pin the schema's source vocabulary to location_snapshot.VALID_SOURCES."""
    from app.transport.services.location_snapshot import VALID_SOURCES
    assert _SOURCE_KEYS == set(VALID_SOURCES)


# --- route behavior: shadow (flag off) --------------------------------------

def test_flag_defaults_false(app):
    assert app.config.get("TRANSPORT_BOOKING_SCHEMA_ENFORCE", False) is False


def test_shadow_valid_form_still_uses_raw_form(
        client, rider_with_kyc, app, patched_booking):
    _login(client, rider_with_kyc)
    assert app.config.get("TRANSPORT_BOOKING_SCHEMA_ENFORCE", False) is False

    resp = client.post("/transport/book", data=_form(),
                       follow_redirects=False)

    assert resp.status_code == 302
    assert len(patched_booking["create"]) == 1
    sent = patched_booking["create"][0]
    assert sent["luggage_count"] == "0"        # raw string, not coerced
    assert sent["pickup_latitude"] == "0.3150"


def test_shadow_mode_logs_discrepancy_and_does_not_reject(
        client, rider_with_kyc, app, patched_booking):
    """Flag off: a schema discrepancy is logged, never rejected."""
    _login(client, rider_with_kyc)
    assert app.config.get("TRANSPORT_BOOKING_SCHEMA_ENFORCE", False) is False

    # migrations/env.py calls logging.config.fileConfig(), whose
    # disable_existing_loggers default disables app.* for the session.
    # Re-enable the route logger and capture on it directly (app.* sets
    # propagate=False).
    route_logger = logging.getLogger("app.transport.routes")
    handler = _ListHandler()
    previous_level = route_logger.level
    previous_disabled = route_logger.disabled
    route_logger.addHandler(handler)
    route_logger.setLevel(logging.INFO)
    route_logger.disabled = False
    try:
        resp = client.post("/transport/book",
                           data=_form(luggage_count="5000"),
                           follow_redirects=False)
    finally:
        route_logger.removeHandler(handler)
        route_logger.setLevel(previous_level)
        route_logger.disabled = previous_disabled

    assert resp.status_code == 302
    # The schema did NOT reject: the real booking path ran with raw form data.
    assert len(patched_booking["create"]) == 1
    sent = patched_booking["create"][0]
    assert sent["luggage_count"] == "5000"
    assert sent["pickup_latitude"] == "0.3150"
    # The discrepancy is observable.
    assert any("SCHEMA-SHADOW" in rec.getMessage() for rec in handler.records)


# --- route behavior: enforcement on (test-local override) -------------------

def test_enforce_mode_rejects_discrepancy_before_service(
        client, rider_with_kyc, app, patched_booking, monkeypatch):
    """Flag on: the schema gates the same discrepancy before the service."""
    _login(client, rider_with_kyc)
    monkeypatch.setitem(app.config, "TRANSPORT_BOOKING_SCHEMA_ENFORCE", True)

    resp = client.post("/transport/book", data=_form(luggage_count="5000"),
                       follow_redirects=False)

    assert resp.status_code == 302
    assert "/transport/" in resp.headers["Location"]  # -> transport.home
    assert patched_booking["create"] == []            # service never ran
