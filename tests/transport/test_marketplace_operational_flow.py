"""Test complete marketplace operational flow: discover -> apply -> approve -> accept -> go-live."""

import pytest
import uuid
from datetime import datetime, timezone

from app.transport.services.marketplace_service import VehicleMarketplaceService
from app.transport.models import (
    Vehicle, DriverProfile, VehicleMarketplaceListing, 
    DriverVehicleApplication, VehicleContract,
    MarketplaceListingStatus, ApplicationStatus, ContractStatus,
    CompensationModel, VerificationTier
)
from app.identity.models.user import User
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import OrganisationMember, OrgRole, OrgUserRole, OrgRolePermission
from app.identity.models.roles_permission import Permission, get_or_create_permission, assign_permission_to_role
from app.transport.services.go_live_service import can_go_live, service_requires_own_vehicle
from app.extensions import db


class TestMarketplaceOperationalFlow:
    """Test complete marketplace operational flow."""

    def _make_user(self, suffix):
        """Create a unique user."""
        return User(
            id=uuid.uuid4().int & ((1 << 63) - 1),
            email=f"user_{suffix}@test.com",
            password_hash="dummy",
            is_verified=True,
            is_active=True,
        )

    def _make_org_user(self, suffix):
        """Create a unique organisation user."""
        return User(
            id=uuid.uuid4().int & ((1 << 63) - 1),
            email=f"org_user_{suffix}@test.com",
            password_hash="dummy",
            is_verified=True,
            is_active=True,
        )

    def _make_organisation(self, suffix):
        """Create a unique organisation."""
        return Organisation(
            id=uuid.uuid4().int & ((1 << 63) - 1),
            legal_name=f"Test Organisation {suffix}",
            org_id=str(uuid.uuid4()),
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

    def _make_driver(self, suffix, user):
        """Create a driver profile."""
        return DriverProfile(
            id=uuid.uuid4().int & ((1 << 63) - 1),
            user_id=user.id,
            driver_code=f"DRV{suffix}",
            verification_tier=VerificationTier.BASIC_VERIFIED,
            compliance_status='approved',
            license_verified=True,
            license_expiry=datetime.now(timezone.utc).replace(year=datetime.now().year + 5),
            license_number_encrypted="enc:dummy",
            service_types=['on_demand'],
        )

    def _make_vehicle(self, suffix, owner_type, owner_id):
        """Create a vehicle."""
        return Vehicle(
            id=uuid.uuid4().int & ((1 << 63) - 1),
            license_plate=f"TEST{suffix}",
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
        )

    def test_complete_flow_org_vehicle_to_driver(self, db_session):
        """Test complete flow: org vehicle -> driver applies -> owner approves -> driver accepts -> go-live."""
        suffix = uuid.uuid4().hex[:8]
        service = VehicleMarketplaceService()

        # 1. Create organisation owner and vehicle
        org_user = self._make_org_user(suffix)
        organisation = self._make_organisation(suffix)
        vehicle = self._make_vehicle(suffix, 'organisation', organisation.id)
        
        db_session.add(org_user)
        db_session.add(organisation)
        db_session.add(vehicle)
        db_session.commit()

        # 2. Create org member with transport permission
        org_member = self._make_org_member_with_transport_permission(suffix, org_user, organisation, db_session)

        # 2b. Create marketplace listing
        listing_data = {
            'required_verification_tier': 'basic_verified',
            'compensation_model': 'revenue_split',
            'driver_revenue_share_pct': 70.00,
            'auto_approve': False,
        }
        listing = service.create_listing(vehicle.id, org_user.id, listing_data)
        assert listing is not None
        assert listing.listing_status == MarketplaceListingStatus.ACTIVE

        # 3. Create driver and apply
        driver_user = self._make_user(suffix + "_driver")
        driver = self._make_driver(suffix + "_driver", driver_user)
        
        db_session.add(driver_user)
        db_session.add(driver)
        db_session.commit()

        # Submit application
        application_data = {
            'cover_letter': 'I am interested in driving this vehicle',
            'proposed_schedule': {'monday': '08:00-17:00'},
            'proposed_hours_per_week': 40,
        }
        application = service.submit_application(driver_user.id, listing.id, application_data)
        assert application is not None
        assert application.status == ApplicationStatus.PENDING

        # 4. Owner approves application
        contract = service.approve_application(application.id, org_user.id)
        assert contract is not None
        assert contract.status == ContractStatus.PENDING_SIGNATURE
        assert contract.vehicle_id == vehicle.id
        assert contract.driver_id == driver.id
        assert contract.owner_id == org_user.id

        # Verify listing status updated
        db_session.refresh(listing)
        assert listing.listing_status == MarketplaceListingStatus.FILLED

        # 5. Driver accepts contract (this is the key marketplace bridge)
        success = service.accept_contract_terms(contract.id, driver_user.id)
        assert success is True

        # 6. Verify contract is now ACTIVE
        db_session.refresh(contract)
        assert contract.status == ContractStatus.ACTIVE
        assert contract.start_date is not None

        # 7. Verify DriverVehicleHistory was created (authoritative relationship)
        from app.transport.models import DriverVehicleHistory
        history = DriverVehicleHistory.query.filter_by(
            driver_id=driver.id,
            vehicle_id=vehicle.id,
            ended_at=None
        ).first()
        
        assert history is not None, "DriverVehicleHistory should be created on contract activation"
        assert history.driver_id == driver.id
        assert history.vehicle_id == vehicle.id
        assert history.ended_at is None
        assert history.assignment_reason == 'marketplace_contract'

        # 8. Verify vehicle.current_driver resolves correctly
        db_session.refresh(vehicle)
        assert vehicle.current_driver is not None
        assert vehicle.current_driver.id == driver.id

        # 9. Verify driver.current_vehicle resolves correctly
        db_session.refresh(driver)
        assert driver.current_vehicle is not None
        assert driver.current_vehicle.id == vehicle.id

        # 10. Verify Go-Live eligibility
        checklist = can_go_live(driver)
        
        # Check vehicle gate passes (driver has vehicle)
        vehicle_check = next((c for c in checklist.checks if c.key == 'vehicle'), None)
        assert vehicle_check is not None
        assert vehicle_check.ok is True, f"Vehicle check should pass but got: {vehicle_check.hint}"
        
        # Overall readiness depends on all gates
        print(f"Go-Live checklist: {checklist.to_dict()}")

        # 11. Verify service_requires_own_vehicle returns True for on-demand
        requires_vehicle = service_requires_own_vehicle(driver)
        assert requires_vehicle is True, "on_demand service type should require vehicle"

    def test_driver_own_vehicle_remains_valid(self, db_session):
        """Test that driver's own vehicle flow remains valid (marketplace not required)."""
        suffix = uuid.uuid4().hex[:8]
        
        # Create driver with own vehicle
        driver_user = self._make_user(suffix + "_own")
        driver = self._make_driver(suffix + "_own", driver_user)
        vehicle = self._make_vehicle(suffix + "_own", 'driver', driver.id)
        
        db_session.add(driver_user)
        db_session.add(driver)
        db_session.add(vehicle)
        db_session.commit()

        # Create DriverVehicleHistory directly (existing mechanism)
        from app.transport.models import assign_driver_to_vehicle
        assignment = assign_driver_to_vehicle(driver, vehicle, reason='ownership')
        db_session.commit()

        # Verify relationship
        db_session.refresh(driver)
        assert driver.current_vehicle is not None
        assert driver.current_vehicle.id == vehicle.id

        # Verify Go-Live works
        checklist = can_go_live(driver)
        vehicle_check = next((c for c in checklist.checks if c.key == 'vehicle'), None)
        assert vehicle_check is not None
        assert vehicle_check.ok is True

    def test_contract_acceptance_without_vehicle_relationship_fails_gracefully(self, db_session):
        """Test that contract activation handles relationship creation failure gracefully."""
        suffix = uuid.uuid4().hex[:8]
        service = VehicleMarketplaceService()

        # Create test data
        org_user = self._make_org_user(suffix)
        organisation = self._make_organisation(suffix)
        driver_user = self._make_user(suffix + "_driver")
        driver = self._make_driver(suffix + "_driver", driver_user)
        vehicle = self._make_vehicle(suffix, 'organisation', organisation.id)
        
        db_session.add(org_user)
        db_session.add(organisation)
        db_session.add(driver_user)
        db_session.add(driver)
        db_session.add(vehicle)
        db_session.commit()
        
        # Create org member with transport permission
        org_member = self._make_org_member_with_transport_permission(suffix, org_user, organisation, db_session)

        # Create listing
        listing = service.create_listing(vehicle.id, org_user.id, {
            'required_verification_tier': 'basic_verified',
            'auto_approve': False,
        })

        # Create application and contract
        application = service.submit_application(driver_user.id, listing.id, {})
        contract = service.approve_application(application.id, org_user.id)
        db_session.commit()

        # Now simulate a failure in assign_driver_to_vehicle by mocking it to raise
        from unittest.mock import patch
        with patch('app.transport.models.assign_driver_to_vehicle', side_effect=Exception("DB error")):
            success = service.accept_contract_terms(contract.id, driver_user.id)
            # Contract activation should still succeed even if relationship creation fails
            assert success is True
            
            # Contract should be ACTIVE
            db_session.refresh(contract)
            assert contract.status == ContractStatus.ACTIVE

    def test_go_live_denied_without_vehicle(self, db_session):
        """Test that Go-Live is denied when driver has no vehicle relationship."""
        suffix = uuid.uuid4().hex[:8]
        
        # Create driver WITHOUT vehicle
        driver_user = self._make_user(suffix + "_nov")
        driver = self._make_driver(suffix + "_nov", driver_user)
        
        db_session.add(driver_user)
        db_session.add(driver)
        db_session.commit()

        # Verify Go-Live is denied
        checklist = can_go_live(driver)
        
        # Vehicle check should fail for on_demand drivers
        vehicle_check = next((c for c in checklist.checks if c.key == 'vehicle'), None)
        assert vehicle_check is not None
        
        # If driver has on_demand service type, vehicle is required
        driver.service_types = ['on_demand']
        requires_vehicle = service_requires_own_vehicle(driver)
        assert requires_vehicle is True
        
        checklist = can_go_live(driver)
        vehicle_check = next((c for c in checklist.checks if c.key == 'vehicle'), None)
        assert vehicle_check is not None
        assert vehicle_check.ok is False, "Vehicle check should fail without vehicle"
        assert "requires an assigned vehicle" in vehicle_check.hint
        
        # Overall readiness should be False
        assert checklist.ready is False

    def test_contract_acceptance_wrong_driver_fails(self, db_session):
        """Test that wrong driver cannot accept contract."""
        suffix = uuid.uuid4().hex[:8]
        service = VehicleMarketplaceService()

        # Create test data
        org_user = self._make_org_user(suffix)
        organisation = self._make_organisation(suffix)
        driver_user = self._make_user(suffix + "_driver")
        other_user = self._make_user(suffix + "_other")
        driver = self._make_driver(suffix + "_driver", driver_user)
        other_driver = self._make_driver(suffix + "_other", other_user)
        vehicle = self._make_vehicle(suffix, 'organisation', organisation.id)
        
        db_session.add(org_user)
        db_session.add(organisation)
        db_session.add(driver_user)
        db_session.add(other_user)
        db_session.add(driver)
        db_session.add(other_driver)
        db_session.add(vehicle)
        db_session.commit()
        
        # Create org member with transport permission
        org_member = self._make_org_member_with_transport_permission(suffix, org_user, organisation, db_session)

        # Create listing, application, contract
        listing = service.create_listing(vehicle.id, org_user.id, {'auto_approve': False})
        application = service.submit_application(driver_user.id, listing.id, {})
        contract = service.approve_application(application.id, org_user.id)
        db_session.commit()

        # Other driver tries to accept - should fail
        success = service.accept_contract_terms(contract.id, other_user.id)
        assert success is False

        # Contract should still be PENDING_SIGNATURE
        db_session.refresh(contract)
        assert contract.status == ContractStatus.PENDING_SIGNATURE

    def test_contract_acceptance_already_active_fails(self, db_session):
        """Test that accepting already active contract fails."""
        suffix = uuid.uuid4().hex[:8]
        service = VehicleMarketplaceService()

        org_user = self._make_org_user(suffix)
        organisation = self._make_organisation(suffix)
        driver_user = self._make_user(suffix + "_driver")
        driver = self._make_driver(suffix + "_driver", driver_user)
        vehicle = self._make_vehicle(suffix, 'organisation', organisation.id)
        
        db_session.add(org_user)
        db_session.add(organisation)
        db_session.add(driver_user)
        db_session.add(driver)
        db_session.add(vehicle)
        db_session.commit()
        
        org_member = self._make_org_member_with_transport_permission(suffix, org_user, organisation, db_session)

        listing = service.create_listing(vehicle.id, org_user.id, {'auto_approve': False})
        application = service.submit_application(driver_user.id, listing.id, {})
        contract = service.approve_application(application.id, org_user.id)
        db_session.commit()

        # First acceptance - should succeed
        success1 = service.accept_contract_terms(contract.id, driver_user.id)
        assert success1 is True

        # Second acceptance - should fail
        success2 = service.accept_contract_terms(contract.id, driver_user.id)
        assert success2 is False

    def test_nonexistent_contract_fails(self, db_session):
        """Test that accepting non-existent contract fails."""
        service = VehicleMarketplaceService()
        success = service.accept_contract_terms(99999, 1)
        assert success is False


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])