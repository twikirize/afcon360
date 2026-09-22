"""Behavioural tests for marketplace UX harmonisation (Part A)."""

import pytest
import uuid
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash

from app.transport.services.marketplace_service import VehicleMarketplaceService
from app.transport.models import (
    Vehicle, DriverProfile, VehicleMarketplaceListing, 
    DriverVehicleApplication, VehicleContract,
    MarketplaceListingStatus, ApplicationStatus, ContractStatus,
    CompensationModel, VerificationTier, DriverVehicleHistory
)
from app.identity.models.user import User
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import OrganisationMember, OrgRole, OrgUserRole, OrgRolePermission
from app.identity.models.roles_permission import Permission, get_or_create_permission, assign_permission_to_role
from app.transport.services.go_live_service import can_go_live, service_requires_own_vehicle
from app.extensions import db
from flask import g, url_for


class TestMarketplaceUXHarmonisation:
    """Behavioural tests for marketplace UX harmonisation (Part A)."""

    def _make_user(self, suffix):
        """Create a unique user."""
        return User(
            id=uuid.uuid4().int & ((1 << 63) - 1),
            email=f"user_{suffix}@test.com",
            password_hash=generate_password_hash("password"),
            is_verified=True,
            is_active=True,
        )

    def _make_org_user(self, suffix):
        """Create a unique organisation user."""
        return User(
            id=uuid.uuid4().int & ((1 << 63) - 1),
            email=f"org_user_{suffix}@test.com",
            password_hash=generate_password_hash("password"),
            is_verified=True,
            is_active=True,
        )

    def _make_organisation(self, suffix):
        """Create a unique organisation."""
        org_id_val = str(uuid.uuid4())
        return Organisation(
            id=uuid.uuid4().int & ((1 << 63) - 1),
            legal_name=f"Test Organisation {suffix}",
            org_id=org_id_val,
            slug=org_id_val,
            country="UG",
        )

    def _make_org_member_with_transport_permission(self, suffix, user, organisation, db_session):
        """Create an organisation member with transport_manager role (has org.transport.manage)."""
        # Create organisation member
        member = OrganisationMember(
            user_id=user.id,
            organisation_id=organisation.id,
            is_active=True,
        )
        db_session.add(member)
        db_session.flush()  # Get member.id
        
        # Get or create the transport_manager role for this organisation
        transport_manager_role = OrgRole.query.filter_by(
            organisation_id=organisation.id,
            template_name='transport_manager'
        ).first()
        
        if not transport_manager_role:
            # Create the OrgRole directly (not using get_or_create_org_role which returns a different model)
            transport_manager_role = OrgRole(
                name='transport_manager',
                organisation_id=organisation.id,
                description='Manages drivers, vehicles, and routes',
                template_name='transport_manager',
            )
            db_session.add(transport_manager_role)
            db_session.flush()
        
        # Create the role assignment
        role_assignment = OrgUserRole(
            organisation_member_id=member.id,
            role_id=transport_manager_role.id,
        )
        db_session.add(role_assignment)
        db_session.flush()
        
        # Ensure permissions are seeded and linked
        from app.identity.models.roles_permission import get_or_create_permission, assign_permission_to_role
        perm = Permission.query.filter_by(name='org.transport.manage').first()
        if not perm:
            perm = get_or_create_permission('org.transport.manage', 'Manage drivers, vehicles, routes', commit=False)
            db_session.flush()
        
        # Link permission to role using OrgRolePermission (not assign_permission_to_role which uses different model)
        existing_link = db_session.query(OrgRolePermission).filter_by(
            org_role_id=transport_manager_role.id,
            permission_id=perm.id
        ).first()
        if not existing_link:
            perm_link = OrgRolePermission(
                org_role_id=transport_manager_role.id,
                permission_id=perm.id,
            )
            db_session.add(perm_link)
        
        db_session.commit()
        return member

    def _make_driver(self, suffix, user, driver_code_suffix=None):
        """Create a driver profile."""
        if driver_code_suffix is None:
            driver_code_suffix = suffix[-8:] if len(suffix) > 8 else suffix
        return DriverProfile(
            id=uuid.uuid4().int & ((1 << 63) - 1),
            user_id=user.id,
            driver_code=f"DRV{driver_code_suffix}",
            verification_tier=VerificationTier.BASIC_VERIFIED,
            compliance_status='approved',
            license_verified=True,
            license_expiry=datetime.now(timezone.utc).replace(year=datetime.now().year + 5),
            license_number_encrypted="enc:dummy",
            service_types=['on_demand'],
        )

    def _make_vehicle(self, suffix, owner_type, owner_id, unique_id=None):
        """Create a vehicle."""
        if unique_id:
            license_plate = f"TEST{suffix}_{unique_id[:6]}"
        else:
            license_plate = f"TEST{suffix}"
        return Vehicle(
            id=uuid.uuid4().int & ((1 << 63) - 1),
            license_plate=license_plate,
            owner_type=owner_type,
            owner_id=owner_id,
            status='active',
            is_available=True,
            is_reserved=False,
            is_deleted=False,
            make="Toyota",
            model="Corolla",
            year=2021,
            vehicle_type="sedan",
            vehicle_class='comfort',
            passenger_capacity=4,
        )

    def _make_listing(self, suffix, vehicle, owner_id):
        """Create a marketplace listing."""
        return VehicleMarketplaceListing(
            id=uuid.uuid4().int & ((1 << 63) - 1),
            vehicle_id=vehicle.id,
            owner_id=owner_id,
            listing_status=MarketplaceListingStatus.ACTIVE,
            visibility='public',
            compensation_model=CompensationModel.REVENUE_SPLIT,
            driver_revenue_share_pct=70.00,
            required_verification_tier=VerificationTier.BASIC_VERIFIED,
            min_vehicle_rating=0.0,
        )

    def test_owner_review_page_access_and_flow(self, client, db_session, unique_id):
        """Test owner can view applications, approve, driver accepts, history created."""
        # Setup: individual user who owns a vehicle and listing
        owner_user = self._make_user(f"owner1_{unique_id}")
        db_session.add(owner_user)
        db_session.commit()
        owner_user_email = owner_user.email
        owner_public_id = str(owner_user.public_id)

        # Driver who will apply
        driver_user = self._make_user(f"driver1_{unique_id}")
        # Use a short suffix for driver_code (max 20 chars)
        driver_code_suffix = unique_id[:8]
        driver_profile = self._make_driver(f"driver1_{unique_id}", driver_user, driver_code_suffix=driver_code_suffix)
        db_session.add_all([driver_user, driver_profile])
        db_session.commit()
        # Store values needed later before session expires
        driver_profile_id = driver_profile.id
        driver_public_id = str(driver_user.public_id)
        driver_code = driver_profile.driver_code
        driver_email = driver_user.email

        # Vehicle owned by the individual user
        vehicle = self._make_vehicle("vehicle1", 'user', owner_user.id, unique_id)
        db_session.add(vehicle)
        db_session.commit()
        vehicle_id = vehicle.id

        # Active listing for the vehicle
        listing = self._make_listing("listing1", vehicle, owner_user.id)
        db.session.add(listing)
        db_session.commit()
        listing_id = listing.id

        # Login as driver and submit application
        login_resp = client.post(
            url_for('auth.login', _external=False),
            data={'username': driver_user.email, 'password': 'password'},
            follow_redirects=True
        )
        resp = client.post(
            url_for('transport_api.vehicle_contract_request', vehicle_id=vehicle_id),
            json={
                'cover_letter': 'I am interested in driving this vehicle',
                'proposed_schedule': {'monday': '08:00-17:00'},
                'proposed_hours_per_week': 40,
            },
            follow_redirects=True
        )
        assert resp.status_code == 200
        # Ensure application was created
        application = DriverVehicleApplication.query.filter_by(
            listing_id=listing_id,
            driver_id=driver_profile_id
        ).first()
        assert application is not None
        assert application.status == ApplicationStatus.PENDING
        application_id = application.id

# Logout driver
        client.post(url_for('auth.logout'))

        # Login as owner (individual user) - use session login like working tests
        # Clear Flask-Login's request-local user cache so the new session identity is resolved.
        g.pop('_login_user', None)
        with client.session_transaction() as sess:
            sess["_user_id"] = owner_public_id
            sess["_fresh"] = True
        print(f"\nDEBUG: Logged in owner via session_transaction")

        # Owner reviews applications page
        review_url = url_for('transport.owner_application_review', listing_id=listing_id)
        resp = client.get(review_url)
        assert resp.status_code == 200
        # Check that the application is shown in the response (by checking for driver code or email)
        assert driver_code.encode() in resp.data or driver_email.encode() in resp.data

        # Owner approves the application via API (simulating the button click)
        resp = client.post(
            url_for(
                'transport_api.marketplace_application_approve',
                application_id=application_id
            ),
            follow_redirects=True
        )
        assert resp.status_code == 200
        # Re-query application after the request boundary and check status
        application = DriverVehicleApplication.query.filter_by(id=application_id).first()
        assert application is not None
        assert application.status == ApplicationStatus.APPROVED

        # Ensure a contract was created
        contract = VehicleContract.query.filter_by(
            application_id=application_id,
            driver_id=driver_profile_id
        ).first()
        assert contract is not None
        contract_id = contract.id
        assert contract.status == ContractStatus.PENDING_SIGNATURE

        # Logout owner
        client.get(url_for('auth.logout'))

        # Login as driver again to accept contract
        g.pop('_login_user', None)
        with client.session_transaction() as sess:
            sess["_user_id"] = driver_public_id
            sess["_fresh"] = True

        # Driver accepts contract via API
        resp = client.post(
            url_for(
                'transport_api.contract_acceptance',
                contract_id=contract_id
            ),
            follow_redirects=True
        )
        assert resp.status_code == 200
        # Re-query contract after the request boundary and check status
        contract = VehicleContract.query.filter_by(id=contract_id).first()
        assert contract is not None
        assert contract.status == ContractStatus.ACTIVE

        # Verify DriverVehicleHistory was created (authoritative relationship)
        history = DriverVehicleHistory.query.filter_by(
            driver_id=driver_profile_id,
            ended_at=None
        ).first()
        assert history is not None
        assert history.driver_id == driver_profile_id
        assert history.vehicle_id == vehicle_id

        # Logout
        client.get(url_for('auth.logout'))

    def test_unauthorized_owner_cannot_view_review_page(self, client, db_session):
        """Test that a user who does not own the listing cannot view the review page."""
        # Create two organisations
        org1_user, org1 = self._make_org_user("org4"), self._make_organisation("org4")
        org1_user.organisation_id = org1.id
        org2_user, org2 = self._make_org_user("org5"), self._make_organisation("org5")
        org2_user.organisation_id = org2.id
        db_session.add_all([org1_user, org2_user, org1, org2])
        db_session.commit()

        # Vehicle owned by org1
        vehicle = self._make_vehicle("vehicle2", 'user', org1_user.id, unique_id=str(uuid.uuid4()))
        db_session.add(vehicle)
        db_session.commit()

        # Active listing for the vehicle by org1
        listing = self._make_listing("listing2", vehicle, org1_user.id)
        db_session.add(listing)
        db_session.commit()
        listing_id = listing.id

        # Login as org2 user (different organisation)
        client.post(
            url_for('auth.login', _external=False),
            data={'email': org2_user.email, 'password': 'password'},
            follow_redirects=True
        )

        # Attempt to access the review page for org1's listing
        resp = client.get(
            url_for('transport.owner_application_review', listing_id=listing_id)
        )
        # Should be forbidden (403) or not found (404) because we check ownership
        assert resp.status_code in (403, 404)

        # Logout
        client.get(url_for('auth.logout'))

    def test_duplicate_driver_application_prevented(self, client, db_session):
        """Test that a driver cannot apply twice to the same listing."""
        # Setup: organisation, vehicle, listing
        org_user, org = self._make_org_user("org3"), self._make_organisation("org3")
        org_user.organisation_id = org.id
        db_session.add(org_user)
        db_session.commit()

        from app.transport.models import Vehicle
        vehicle = self._make_vehicle("vehicle3", 'user', org_user.id)
        db_session.add(vehicle)
        db_session.commit()
        vehicle_id = vehicle.id

        listing = self._make_listing("listing3", vehicle, org_user.id)
        db_session.add(listing)
        db_session.commit()
        listing_id = listing.id

        # Driver
        driver_user = self._make_user("driver2")
        driver_profile = self._make_driver("driver2", driver_user)
        db_session.add_all([driver_user, driver_profile])
        db_session.commit()
        driver_profile_id = driver_profile.id

        # Login as driver and apply first time
        client.post(
            url_for('auth.login', _external=False),
            data={'email': driver_user.email, 'password': 'password'},
            follow_redirects=True
        )
        resp1 = client.post(
            url_for('transport_api.vehicle_contract_request', vehicle_id=vehicle_id),
            json={},
            follow_redirects=True
        )
        assert resp1.status_code == 200

        # Try to apply again
        resp2 = client.post(
            url_for('transport_api.vehicle_contract_request', vehicle_id=vehicle_id),
            json={},
            follow_redirects=True
        )
        # Should fail with a validation error (maybe 400 or 200 with error message)
        # We'll assume the endpoint returns 200 but with an error flash or JSON error.
        # For simplicity, we'll check that the application count is still 1.
        applications = DriverVehicleApplication.query.filter_by(
            listing_id=listing_id,
            driver_id=driver_profile_id
        ).all()
        assert len(applications) == 1

        # Logout
        client.get(url_for('auth.logout'))