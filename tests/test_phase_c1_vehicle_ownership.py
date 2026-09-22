"""
Phase C-1: Vehicle Ownership / Management independence regression tests.

Contract under test
-------------------
Ownership of a transport vehicle is INDEPENDENT of Driver Workspace
participation.  A vehicle may be owned by:

  * a DriverProfile        -- ``owner_type='driver'`` / ``owner_id=DriverProfile.id``
  * a User (personal owner)-- ``owner_type='user'``   / ``owner_id=User.id``
  * an Organisation (fleet)-- ``owner_type='organisation'`` / ``owner_id=Organisation.id``

Ownership is NOT assignment.  ``DriverVehicleHistory`` records who is
*assigned* to operate a vehicle for a period; it never creates ownership.
One human may simultaneously be a driver-owner, a personal owner, an
organisation fleet manager and an assigned operator.

These tests are additive.  They assert the approved Phase C-1 behaviour
and do not rewrite any pre-existing test (the two superseded Stage 4B-5
``get_user_vehicles`` tests are reconciled separately).
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import (
    OrgRole,
    OrgUserRole,
    OrganisationMember,
)
from app.transport.models import (
    ComplianceStatus,
    DriverProfile,
    DriverVehicleHistory,
    Vehicle,
    VehicleClass,
    VerificationTier,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db_session, suffix=None):
    from app.identity.models.user import User

    suffix = suffix or uuid.uuid4().hex[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"pc1_{suffix}",
        email=f"pc1_{suffix}@example.com",
    )
    user.set_password("TestPassword123!")
    user.is_active = True
    user.is_verified = True
    db_session.add(user)
    db_session.flush()
    return user


def _make_kyc_verification(db_session, user):
    """Give *user* a verified KYC identity broad enough to reach tier >= 3."""
    from app.identity.individuals.individual_verification import (
        IndividualVerification,
    )

    user.phone_verified = True
    user.phone_verified_at = datetime.now(timezone.utc)
    if not user.phone:
        user.phone = f"+2567{uuid.uuid4().hex[:7]}"
    db_session.add(
        IndividualVerification(
            user_id=user.id,
            status="verified",
            scope={
                "identity": True,
                "address": True,
                "national_id": True,
                "biometric": True,
                "tax": True,
                "financial": True,
            },
        )
    )
    db_session.flush()
    return user


def _make_driver_profile(db_session, user, compliance=ComplianceStatus.APPROVED):
    suffix = uuid.uuid4().hex[:8]
    driver = DriverProfile(
        user_id=user.id,
        driver_code=f"PC1-{suffix[:6].upper()}",
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
    )
    db_session.add(vehicle)
    db_session.flush()
    return vehicle


def _assign(db_session, driver_profile_id, vehicle_id, reason="shift_start"):
    row = DriverVehicleHistory(
        driver_id=driver_profile_id,
        vehicle_id=vehicle_id,
        started_at=datetime.now(timezone.utc),
        ended_at=None,
        assignment_reason=reason,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _make_org(db_session, suffix=None):
    suffix = suffix or uuid.uuid4().hex[:8]
    org = Organisation(
        legal_name=f"Phase C1 Org {suffix}",
        org_id=str(uuid.uuid4()),
        country="UG",
    )
    db_session.add(org)
    db_session.flush()
    return org


def _assign_org_role(db_session, user, org, role_name):
    from app.identity.services.organisation_role_provisioning import (
        provision_organisation_roles,
    )

    provision_organisation_roles(org, commit=False)
    db_session.flush()
    membership = OrganisationMember(
        user_id=user.id,
        organisation_id=org.id,
        is_active=True,
    )
    db_session.add(membership)
    db_session.flush()
    org_role = OrgRole.query.filter_by(
        organisation_id=org.id, name=role_name,
    ).first()
    assert org_role is not None, f"org role {role_name!r} was not provisioned"
    db_session.add(
        OrgUserRole(
            organisation_member_id=membership.id,
            role_id=org_role.id,
            assigned_by=user.id,
        )
    )
    db_session.flush()
    return membership


def _vehicle_payload(plate="PC1-001"):
    """Union payload satisfying both the validator's required keys and the
    internal registration keys (two coexisting field vocabularies)."""
    return {
        "plate_number": plate,
        "license_plate": plate,
        "make": "Toyota",
        "model": "Corolla",
        "year": 2021,
        "vehicle_class": "comfort",
        "capacity": 4,
        "passenger_capacity": 4,
        "luggage_capacity": 2,
        "color": "White",
        "vehicle_type": "sedan",
    }


def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = user.public_id
        sess["_fresh"] = True


def _seed_route_user(app, *, kyc=False, driver=False,
                     compliance=ComplianceStatus.APPROVED):
    """Create a User (+ optional DriverProfile / KYC) for route tests."""
    with app.app_context():
        from app.extensions import db

        user = _make_user(db.session)
        driver_id = None
        if driver:
            driver = _make_driver_profile(db.session, user, compliance=compliance)
            driver_id = driver.id
        if kyc:
            _make_kyc_verification(db.session, user)
        db.session.commit()
        return SimpleNamespace(
            id=user.id,
            public_id=user.public_id,
            driver_profile_id=driver_id,
        )


def _route_vehicle(app, owner_type, owner_id, plate):
    with app.app_context():
        from app.extensions import db

        vehicle = _make_vehicle(db.session, owner_type, owner_id, plate)
        db.session.commit()
        return vehicle.id


# ===========================================================================
# Ownership multiplicity
# ===========================================================================


class TestOwnershipMultiplicity:
    def test_personal_user_registers_and_owns_vehicle_via_service(self, db_session):
        from app.transport.services.provider_service import ProviderService

        user = _make_user(db_session)
        db_session.commit()

        result = ProviderService().register_vehicle(
            owner_type="user",
            owner_id=user.id,
            vehicle_data=_vehicle_payload("PC1-AAA"),
        )

        assert result["success"] is True
        vehicle = Vehicle.query.filter_by(
            owner_type="user", owner_id=user.id,
        ).one()
        assert vehicle.license_plate == "PC1-AAA"
        assert result["data"]["vehicle_id"] == vehicle.id

    def test_one_user_can_own_multiple_personal_vehicles(self, db_session):
        from app.transport.services.provider_service import ProviderService

        user = _make_user(db_session)
        svc = ProviderService()
        svc.register_vehicle(
            owner_type="user", owner_id=user.id,
            vehicle_data=_vehicle_payload("PC1-M1"),
        )
        svc.register_vehicle(
            owner_type="user", owner_id=user.id,
            vehicle_data=_vehicle_payload("PC1-M2"),
        )

        plates = {
            v.license_plate for v in svc.get_user_vehicles(user.id)
        }
        assert plates == {"PC1-M1", "PC1-M2"}

    def test_driver_owner_and_personal_owner_coexist_for_one_user(self, db_session):
        from app.transport.services.provider_service import ProviderService

        user = _make_user(db_session)
        driver = _make_driver_profile(db_session, user)
        _make_vehicle(db_session, "driver", driver.id, "PC1-DRV")
        _make_vehicle(db_session, "user", user.id, "PC1-PER")
        db_session.commit()

        plates = {
            v.license_plate
            for v in ProviderService().get_user_vehicles(user.id)
        }
        assert plates == {"PC1-DRV", "PC1-PER"}

    def test_get_user_vehicles_never_returns_another_users_vehicles(self, db_session):
        from app.transport.services.provider_service import ProviderService

        user = _make_user(db_session)
        other = _make_user(db_session)
        _make_vehicle(db_session, "user", user.id, "PC1-MINE")
        _make_vehicle(db_session, "user", other.id, "PC1-THEIRS")
        db_session.commit()

        plates = {
            v.license_plate
            for v in ProviderService().get_user_vehicles(user.id)
        }
        assert plates == {"PC1-MINE"}


# ===========================================================================
# Assignment vs ownership
# ===========================================================================


class TestAssignmentSemantics:
    def test_assignment_grants_operation_not_ownership(self, db_session):
        from app.transport.services.provider_service import ProviderService

        owner = _make_user(db_session)
        operator = _make_user(db_session)
        owner_driver = _make_driver_profile(db_session, owner)
        operator_driver = _make_driver_profile(db_session, operator)
        vehicle = _make_vehicle(db_session, "driver", owner_driver.id, "PC1-ASN")
        _assign(db_session, operator_driver.id, vehicle.id)
        db_session.commit()

        svc = ProviderService()
        # Ownership is unchanged by the assignment.
        assert vehicle.owner_type == "driver"
        assert vehicle.owner_id == owner_driver.id
        # The operator does not own the vehicle...
        assert svc.get_user_vehicles(operator.id) == []
        # ...but the owner still does, and the operator is the current driver.
        assert [v.id for v in svc.get_user_vehicles(owner.id)] == [vehicle.id]
        assert operator_driver.current_vehicle is not None
        assert operator_driver.current_vehicle.id == vehicle.id

    def test_reassignment_preserves_history_and_updates_current(self, db_session):
        owner = _make_user(db_session)
        driver = _make_driver_profile(db_session, _make_user(db_session))
        v1 = _make_vehicle(db_session, "driver", owner.id, "PC1-H1")
        v2 = _make_vehicle(db_session, "driver", owner.id, "PC1-H2")
        first = _assign(db_session, driver.id, v1.id)
        db_session.commit()

        # Reassign: close the first history row, open the second.
        first.ended_at = datetime.now(timezone.utc)
        _assign(db_session, driver.id, v2.id)
        db_session.commit()

        rows = DriverVehicleHistory.query.filter_by(driver_id=driver.id).all()
        assert len(rows) == 2
        open_rows = [r for r in rows if r.ended_at is None]
        assert len(open_rows) == 1
        assert open_rows[0].vehicle_id == v2.id
        assert driver.current_vehicle.id == v2.id
        # Ownership was never derived from or changed by assignment.
        assert {v1.owner_type, v2.owner_type} == {"driver"}
        assert {v1.owner_id, v2.owner_id} == {owner.id}

    def test_personal_owner_may_assign_another_driver(self, db_session):
        from app.transport.services.provider_service import ProviderService

        owner = _make_user(db_session)
        driver = _make_driver_profile(db_session, _make_user(db_session))
        vehicle = _make_vehicle(db_session, "user", owner.id, "PC1-LEND")
        _assign(db_session, driver.id, vehicle.id)
        db_session.commit()

        # The lending driver operates but does not own it.
        assert ProviderService().get_user_vehicles(driver.user_id) == []
        assert driver.current_vehicle.id == vehicle.id
        # The personal owner keeps ownership.
        assert vehicle.owner_type == "user"
        assert vehicle.owner_id == owner.id


# ===========================================================================
# Organisation fleet authority
# ===========================================================================


class TestOrganisationFleetAuthority:
    def test_org_transport_manager_can_access_org_vehicle(self, db_session, app):
        from app.transport.services.provider_service import ProviderService

        manager = _make_user(db_session)
        org = _make_org(db_session)
        _assign_org_role(db_session, manager, org, "transport_manager")
        vehicle = _make_vehicle(db_session, "organisation", org.id, "PC1-ORG")
        db_session.commit()

        # The canonical permission resolves for the org transport manager.
        from app.identity.services.organization_permissions import (
            OrganizationPermissionService,
        )

        assert OrganizationPermissionService.has_permission(
            manager, org, "org.transport.manage"
        )
        # Fleet ownership is never conflated with personal ownership.
        assert ProviderService().get_user_vehicles(manager.id) == []

    def test_org_transport_manager_can_reach_org_vehicle_route(self, app, client):
        with app.app_context():
            from app.extensions import db

            manager = _make_user(db.session)
            org = _make_org(db.session)
            _assign_org_role(db.session, manager, org, "transport_manager")
            vehicle = _make_vehicle(db.session, "organisation", org.id, "PC1-ORGR")
            db.session.commit()
            manager_public_id = manager.public_id
            vehicle_id = vehicle.id

        with client.session_transaction() as sess:
            sess["_user_id"] = manager_public_id
            sess["_fresh"] = True

        resp = client.get(
            f"/transport/vehicles/{vehicle_id}/edit",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200

    def test_non_member_cannot_reach_org_vehicle_route(self, app, client):
        with app.app_context():
            from app.extensions import db

            outsider = _make_user(db.session)
            org = _make_org(db.session)
            vehicle = _make_vehicle(db.session, "organisation", org.id, "PC1-ORGN")
            db.session.commit()
            outsider_public_id = outsider.public_id
            vehicle_id = vehicle.id

        with client.session_transaction() as sess:
            sess["_user_id"] = outsider_public_id
            sess["_fresh"] = True

        resp = client.get(f"/transport/vehicles/{vehicle_id}/edit")
        assert resp.status_code == 403

    def test_org_member_without_transport_permission_is_denied(self, app, client):
        with app.app_context():
            from app.extensions import db

            member = _make_user(db.session)
            org = _make_org(db.session)
            _assign_org_role(db.session, member, org, "finance_manager")
            vehicle = _make_vehicle(db.session, "organisation", org.id, "PC1-ORGF")
            db.session.commit()
            member_public_id = member.public_id
            vehicle_id = vehicle.id

        with client.session_transaction() as sess:
            sess["_user_id"] = member_public_id
            sess["_fresh"] = True

        resp = client.get(f"/transport/vehicles/{vehicle_id}/edit")
        assert resp.status_code == 403


# ===========================================================================
# Cross-owner route access
# ===========================================================================


class TestCrossOwnerRouteAccess:
    def test_personal_owner_can_reach_own_vehicle_routes(self, app, client):
        owner = _seed_route_user(app)
        vehicle_id = _route_vehicle(app, "user", owner.id, "PC1-ROWN")
        _login(client, owner)

        assert client.get(
            f"/transport/vehicles/{vehicle_id}",
        ).status_code == 200
        assert client.get(
            f"/transport/vehicles/{vehicle_id}/edit",
            headers={"Accept": "application/json"},
        ).status_code == 200

    def test_unrelated_user_is_denied_personal_vehicle(self, app, client):
        owner = _seed_route_user(app)
        other = _seed_route_user(app)
        vehicle_id = _route_vehicle(app, "user", owner.id, "PC1-PRIV")
        _login(client, other)

        # Edit re-raises the authorization failure for HTML clients.
        assert client.get(
            f"/transport/vehicles/{vehicle_id}/edit"
        ).status_code == 403
        # Show refuses to render the foreign vehicle (redirect/deny, never 200).
        assert client.get(
            f"/transport/vehicles/{vehicle_id}"
        ).status_code != 200

    def test_driver_owner_can_reach_own_vehicle_routes(self, app, client):
        owner = _seed_route_user(app, driver=True)
        vehicle_id = _route_vehicle(
            app, "driver", owner.driver_profile_id, "PC1-RDRV",
        )
        _login(client, owner)

        assert client.get(
            f"/transport/vehicles/{vehicle_id}/edit",
            headers={"Accept": "application/json"},
        ).status_code == 200


# ===========================================================================
# Registration route: non-driver personal owner and approved driver
# ===========================================================================


class TestRegistrationRoute:
    def _post_registration(self, client):
        return client.post(
            "/transport/register-vehicle",
            data=_vehicle_payload(f"PC1-{uuid.uuid4().hex[:5].upper()}"),
        )

    def test_non_driver_personal_owner_can_register_via_route(self, app, client):
        owner = _seed_route_user(app, kyc=True)

        with app.app_context():
            from app.auth.kyc_compliance import calculate_kyc_tier

            assert calculate_kyc_tier(owner.id)["tier"] >= 3

        _login(client, owner)
        resp = self._post_registration(client)

        assert resp.status_code in (302, 303)
        assert "/transport/vehicle-dashboard" in resp.headers.get("Location", "")

        with app.app_context():
            from app.extensions import db

            vehicle = Vehicle.query.filter_by(
                owner_type="user", owner_id=owner.id,
            ).one()
            assert vehicle.is_deleted is False

    def test_approved_driver_registers_as_driver_owner_via_route(self, app, client):
        owner = _seed_route_user(app, kyc=True, driver=True)

        with app.app_context():
            from app.auth.kyc_compliance import calculate_kyc_tier

            assert calculate_kyc_tier(owner.id)["tier"] >= 3

        _login(client, owner)
        resp = self._post_registration(client)

        assert resp.status_code in (302, 303)

        with app.app_context():
            from app.extensions import db

            vehicle = Vehicle.query.filter_by(
                owner_type="driver", owner_id=owner.driver_profile_id,
            ).one()
            assert vehicle.owner_id == owner.driver_profile_id


# ===========================================================================
# My Vehicles surface reflects both ownership mappings
# ===========================================================================


class TestVehicleDashboardSurface:
    def test_dashboard_renders_driver_and_personal_vehicles(self, app, client):
        owner = _seed_route_user(app, kyc=True, driver=True)
        with app.app_context():
            from app.extensions import db

            _make_vehicle(db.session, "driver", owner.driver_profile_id, "PC1-DASH-D")
            _make_vehicle(db.session, "user", owner.id, "PC1-DASH-U")
            db.session.commit()

        _login(client, owner)
        resp = client.get("/transport/vehicle-dashboard")

        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "PC1-DASH-D" in body
        assert "PC1-DASH-U" in body
