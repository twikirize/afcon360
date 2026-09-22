"""Test organisation ownership verification in marketplace service."""

import pytest
import uuid
from unittest.mock import Mock, patch

from app.transport.services.marketplace_service import VehicleMarketplaceService
from app.identity.models.user import User
from app.identity.models.organisation import Organisation
from app.transport.models import Vehicle


class TestMarketplaceServiceOrganisationOwnership:
    """Test organisation ownership verification in marketplace service."""

    def _make_org_user(self, suffix):
        """Create a unique organisation user."""
        return User(
            id=uuid.uuid4().int & ((1 << 63) - 1),
            email=f"org_user_{suffix}@test.com",
            password_hash="dummy"
        )

    def _make_organisation(self, suffix):
        """Create a unique organisation."""
        return Organisation(
            id=uuid.uuid4().int & ((1 << 63) - 1),
            legal_name=f"Test Organisation {suffix}",
            org_id=str(uuid.uuid4()),
            country="UG"
        )

    def _make_user(self, suffix):
        """Create a unique regular user."""
        return User(
            id=uuid.uuid4().int & ((1 << 63) - 1),
            email=f"user_{suffix}@test.com",
            password_hash="dummy"
        )

    def _make_vehicle(self, suffix, owner_type, owner_id):
        """Create a vehicle (not persisted)."""
        return Vehicle(
            id=uuid.uuid4().int & ((1 << 63) - 1),
            license_plate=f"TEST{suffix}",
            owner_type=owner_type,
            owner_id=owner_id,
            status='active',
            is_available=True,
            is_reserved=False,
            is_deleted=False
        )

    def test_organisation_owner_with_transport_permission_can_list_vehicle(self, db_session):
        """Test that organisation user with transport permission can list organisation-owned vehicle."""
        suffix = uuid.uuid4().hex[:8]
        service = VehicleMarketplaceService()
        
        org_user = self._make_org_user(suffix)
        organisation = self._make_organisation(suffix)
        vehicle = self._make_vehicle(suffix, 'organisation', organisation.id)
        
        db_session.add(org_user)
        db_session.add(organisation)
        db_session.commit()
        
        with patch('app.identity.services.organization_permissions.OrganizationPermissionService.has_permission') as mock_has_permission:
            mock_has_permission.return_value = True
            
            result = service._verify_vehicle_ownership(vehicle, org_user.id)
            
            assert result is True
            mock_has_permission.assert_called_once_with(org_user, organisation, 'org.transport.manage')

    def test_organisation_owner_without_transport_permission_cannot_list_vehicle(self, db_session):
        """Test that organisation user without transport permission cannot list organisation-owned vehicle."""
        suffix = uuid.uuid4().hex[:8]
        service = VehicleMarketplaceService()
        
        org_user = self._make_org_user(suffix)
        organisation = self._make_organisation(suffix)
        vehicle = self._make_vehicle(suffix, 'organisation', organisation.id)
        
        db_session.add(org_user)
        db_session.add(organisation)
        db_session.commit()
        
        with patch('app.identity.services.organization_permissions.OrganizationPermissionService.has_permission') as mock_has_permission:
            mock_has_permission.return_value = False
            
            result = service._verify_vehicle_ownership(vehicle, org_user.id)
            
            assert result is False
            mock_has_permission.assert_called_once_with(org_user, organisation, 'org.transport.manage')

    def test_non_member_organisation_user_cannot_list_vehicle(self, db_session):
        """Test that user who is not a member of the organisation cannot list vehicle."""
        suffix = uuid.uuid4().hex[:8]
        service = VehicleMarketplaceService()
        
        org_user = self._make_org_user(suffix)
        organisation = self._make_organisation(suffix)
        vehicle = self._make_vehicle(suffix, 'organisation', organisation.id)
        
        db_session.add(org_user)
        db_session.add(organisation)
        db_session.commit()
        
        result = service._verify_vehicle_ownership(vehicle, org_user.id)
        
        assert result is False

    def test_individual_owner_behavior_preserved(self, db_session):
        """Test that individual owner behavior is preserved."""
        suffix = uuid.uuid4().hex[:8]
        service = VehicleMarketplaceService()
        
        user = self._make_user(suffix)
        driver = Mock()
        driver.id = user.id
        
        vehicle = self._make_vehicle(suffix, 'driver', driver.id)
        
        db_session.add(user)
        db_session.commit()
        
        # Mock the entire query chain
        mock_query = Mock()
        mock_query.filter_by.return_value.first.return_value = driver
        with patch('app.transport.models.DriverProfile.query', mock_query):
            
            result = service._verify_vehicle_ownership(vehicle, user.id)
            
            assert result is True
            mock_query.filter_by.assert_called_once_with(user_id=user.id, is_deleted=False)

    def test_user_owner_behavior_preserved(self, db_session):
        """Test that regular user owner behavior is preserved."""
        suffix = uuid.uuid4().hex[:8]
        service = VehicleMarketplaceService()
        
        user = self._make_user(suffix)
        vehicle = self._make_vehicle(suffix, 'user', user.id)
        
        db_session.add(user)
        db_session.commit()
        
        result = service._verify_vehicle_ownership(vehicle, user.id)
        
        assert result is True

    def test_non_owner_cannot_list_vehicle(self, db_session):
        """Test that non-owner cannot list vehicle."""
        suffix = uuid.uuid4().hex[:8]
        service = VehicleMarketplaceService()
        
        user = self._make_user(suffix)
        other_user = self._make_user(suffix + "_other")
        
        vehicle = self._make_vehicle(suffix, 'user', other_user.id)
        
        db_session.add(user)
        db_session.add(other_user)
        db_session.commit()
        
        result = service._verify_vehicle_ownership(vehicle, user.id)
        
        assert result is False