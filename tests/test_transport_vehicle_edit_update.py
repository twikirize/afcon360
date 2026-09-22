"""
Regression tests: vehicle edit persistence.

Contract under test
-------------------
``POST /transport/vehicles/<id>/edit`` persists the editable specification
fields of a vehicle (replacing the previous GET-only behaviour that answered
405 Method Not Allowed on save). Ownership, status, availability, insurance,
QR/verification and assignment state are preserved.

Rules verified here
-------------------
* owner (or an admin) may update the vehicle via the edit route;
* the update goes through ``ProviderService.update_vehicle`` which reuses the
  canonical ``validate_vehicle_registration`` validator;
* unrelated users are denied (403);
* a duplicate license plate is rejected as a conflict;
* protected state (owner_type / owner_id / status / is_available) is never
  changed by an edit.
"""
import uuid
from types import SimpleNamespace

from app.transport.models import (
    ComplianceStatus,
    DriverProfile,
    Vehicle,
    VehicleClass,
    VerificationTier,
)


def _make_user(db_session, suffix=None):
    from app.identity.models.user import User

    suffix = suffix or uuid.uuid4().hex[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"ped_{suffix}",
        email=f"ped_{suffix}@example.com",
    )
    user.set_password("TestPassword123!")
    user.is_active = True
    user.is_verified = True
    db_session.add(user)
    db_session.flush()
    return user


def _make_driver_profile(db_session, user, compliance=ComplianceStatus.APPROVED):
    suffix = uuid.uuid4().hex[:8]
    driver = DriverProfile(
        user_id=user.id,
        driver_code=f"PED-{suffix[:6].upper()}",
        verification_tier=VerificationTier.BASIC_VERIFIED,
        compliance_status=compliance,
        is_active=True,
        is_online=False,
        is_available=False,
        max_passenger_capacity=4,
        vehicle_classes=["comfort"],
    )
    db_session.add(driver)
    db_session.flush()
    return driver


def _make_vehicle(db_session, owner_type, owner_id, plate,
                  vehicle_class=VehicleClass.COMFORT):
    vehicle = Vehicle(
        owner_type=owner_type,
        owner_id=owner_id,
        license_plate=plate,
        make="Toyota",
        model="Corolla",
        year=2021,
        vehicle_type="sedan",
        vehicle_class=vehicle_class,
        passenger_capacity=4,
        status="active",
        is_available=True,
    )
    db_session.add(vehicle)
    db_session.flush()
    return vehicle


def _edit_payload(plate="PED-EDIT"):
    """Form payload for the edit route (union of both field vocabularies,
    matching what the shared ``_form.html`` submits)."""
    return {
        "license_plate": plate,
        "plate_number": plate,
        "registration_number": "REG-2021",
        "make": "Honda",
        "model": "Accord",
        "year": "2022",
        "vehicle_type": "sedan",
        "vehicle_class": "premium",
        "passenger_capacity": "5",
        "capacity": "5",
        "luggage_capacity": "3",
        "color": "Black",
        "vin_number": "1HGCV1F34KA000001",
    }


def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = user.public_id
        sess["_fresh"] = True


def _seed_route_user(app, *, driver=False):
    with app.app_context():
        from app.extensions import db

        user = _make_user(db.session)
        driver_id = None
        if driver:
            driver = _make_driver_profile(db.session, user)
            driver_id = driver.id
        db.session.commit()
        return SimpleNamespace(
            id=user.id,
            public_id=user.public_id,
            driver_profile_id=driver_id,
        )


def _route_vehicle(app, owner_type, owner_id, plate, **kwargs):
    with app.app_context():
        from app.extensions import db

        vehicle = _make_vehicle(db.session, owner_type, owner_id, plate, **kwargs)
        db.session.commit()
        return vehicle.id


def _get_vehicle(app, vehicle_id):
    with app.app_context():
        from app.extensions import db

        return db.session.get(Vehicle, vehicle_id)


# ===========================================================================
# Route-level update behaviour
# ===========================================================================


class TestEditRoute:
    def test_post_persists_edits_and_redirects_to_show(self, app, client):
        owner = _seed_route_user(app)
        vehicle_id = _route_vehicle(app, "user", owner.id, "PED-01")
        _login(client, owner)

        resp = client.post(
            f"/transport/vehicles/{vehicle_id}/edit",
            data=_edit_payload("PED-01"),
        )

        assert resp.status_code in (302, 303)
        assert f"/transport/vehicles/{vehicle_id}" in resp.headers.get("Location", "")

        vehicle = _get_vehicle(app, vehicle_id)
        assert vehicle.make == "Honda"
        assert vehicle.model == "Accord"
        assert vehicle.year == 2022
        assert vehicle.passenger_capacity == 5
        assert vehicle.luggage_capacity == 3
        assert vehicle.color == "Black"
        assert vehicle.vehicle_class == VehicleClass.PREMIUM
        assert vehicle.vin_number == "1HGCV1F34KA000001"

    def test_post_was_previously_405_get_still_renders(self, app, client):
        owner = _seed_route_user(app)
        vehicle_id = _route_vehicle(app, "user", owner.id, "PED-02")
        _login(client, owner)

        assert client.get(
            f"/transport/vehicles/{vehicle_id}/edit",
        ).status_code == 200

        resp = client.post(
            f"/transport/vehicles/{vehicle_id}/edit",
            data=_edit_payload("PED-02"),
        )
        assert resp.status_code != 405

    def test_invalid_payload_redirects_back_and_does_not_change(self, app, client):
        owner = _seed_route_user(app)
        vehicle_id = _route_vehicle(app, "user", owner.id, "PED-03")
        _login(client, owner)

        payload = _edit_payload("PED-03")
        payload["year"] = "1700"
        resp = client.post(
            f"/transport/vehicles/{vehicle_id}/edit",
            data=payload,
        )

        assert resp.status_code in (302, 303)
        assert f"/transport/vehicles/{vehicle_id}/edit" in resp.headers.get("Location", "")

        vehicle = _get_vehicle(app, vehicle_id)
        assert vehicle.year == 2021
        assert vehicle.make == "Toyota"

    def test_unrelated_user_is_denied_update(self, app, client):
        owner = _seed_route_user(app)
        other = _seed_route_user(app)
        vehicle_id = _route_vehicle(app, "user", owner.id, "PED-04")
        _login(client, other)

        resp = client.post(
            f"/transport/vehicles/{vehicle_id}/edit",
            data=_edit_payload("PED-04"),
        )
        assert resp.status_code == 403


class TestEditRouteProtectedState:
    def test_update_preserves_ownership_and_status(self, app, client):
        owner = _seed_route_user(app)
        vehicle_id = _route_vehicle(app, "user", owner.id, "PED-06")
        _login(client, owner)

        client.post(
            f"/transport/vehicles/{vehicle_id}/edit",
            data=_edit_payload("PED-06"),
        )

        vehicle = _get_vehicle(app, vehicle_id)
        assert vehicle.owner_type == "user"
        assert vehicle.owner_id == owner.id
        assert vehicle.status == "active"
        assert vehicle.is_available is True
        # Sensitive fields are untouched.
        assert vehicle.qr_code_hash is None
        assert vehicle.verification_code is None

    def test_driver_owner_can_update_own_vehicle(self, app, client):
        owner = _seed_route_user(app, driver=True)
        vehicle_id = _route_vehicle(
            app, "driver", owner.driver_profile_id, "PED-07",
        )
        _login(client, owner)

        resp = client.post(
            f"/transport/vehicles/{vehicle_id}/edit",
            data=_edit_payload("PED-07"),
        )
        assert resp.status_code in (302, 303)


# ===========================================================================
# Service-level persistence rules
# ===========================================================================


class TestUpdateVehicleService:
    def test_duplicate_plate_is_rejected(self, db_session):
        from app.transport.services.provider_service import ProviderService
        from app.utils.exceptions import ConflictError

        owner = _make_user(db_session)
        _make_vehicle(db_session, "user", owner.id, "PED-DUP1")
        vehicle_id = _make_vehicle(db_session, "user", owner.id, "PED-DUP2").id
        db_session.commit()

        payload = _edit_payload("PED-DUP1")

        try:
            ProviderService().update_vehicle(vehicle_id, payload)
        except ConflictError:
            pass
        else:
            raise AssertionError("duplicate plate must raise ConflictError")

        db_session.rollback()
        vehicle = db_session.get(Vehicle, vehicle_id)
        assert vehicle.license_plate == "PED-DUP2"

    def test_missing_required_field_raises_validation_error(self, db_session):
        from app.transport.services.provider_service import ProviderService
        from app.utils.exceptions import ValidationError

        owner = _make_user(db_session)
        vehicle = _make_vehicle(db_session, "user", owner.id, "PED-VAL")
        db_session.commit()

        payload = _edit_payload("PED-VAL")
        del payload["color"]
        try:
            ProviderService().update_vehicle(vehicle.id, payload)
        except ValidationError:
            pass
        else:
            raise AssertionError("missing color must raise ValidationError")