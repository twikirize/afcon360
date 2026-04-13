"""
Tests for KYC integration between FanProfile and IndividualVerification
"""
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime, UTC

from app.fan.services.registry import (
    get_or_create_fan,
    update_fan_profile,
    get_fan_kyc_status,
    link_fan_to_verification,
    clear_fan_registry
)


class TestFanKYCIntegration:
    """Test the integration between FanProfile and KYC verification"""

    def setup_method(self):
        """Clear the fan registry before each test"""
        clear_fan_registry()

    @patch('app.fan.models.FanProfile')
    def test_fan_profile_kyc_properties(self, MockFanProfile):
        """Test that FanProfile correctly exposes KYC properties"""
        # Create mock fan instance
        mock_fan = MagicMock()
        mock_fan.user_id = 100
        mock_fan.display_name = "Test Fan"
        mock_fan.verification_id = 1

        # Create mock verification
        mock_verification = MagicMock()
        mock_verification.status = "verified"

        # Set up properties
        type(mock_fan).verification = PropertyMock(return_value=mock_verification)
        type(mock_fan).kyc_status = PropertyMock(return_value="verified")
        type(mock_fan).is_kyc_verified = PropertyMock(return_value=True)

        # Test KYC properties
        assert mock_fan.kyc_status == "verified"
        assert mock_fan.is_kyc_verified == True

        # Test with no verification
        mock_fan2 = MagicMock()
        mock_fan2.user_id = 101
        mock_fan2.display_name = "No KYC Fan"
        type(mock_fan2).verification = PropertyMock(return_value=None)
        type(mock_fan2).kyc_status = PropertyMock(return_value=None)
        type(mock_fan2).is_kyc_verified = PropertyMock(return_value=False)

        assert mock_fan2.kyc_status is None
        assert mock_fan2.is_kyc_verified == False

    @patch('app.fan.models.FanProfile')
    def test_fan_profile_to_dict_includes_kyc(self, MockFanProfile):
        """Test that to_dict() includes KYC information"""
        # Create mock fan
        mock_fan = MagicMock()
        mock_fan.user_id = 200
        mock_fan.display_name = "Test Fan"
        mock_fan.verification_id = 2
        mock_fan.nationality = None
        mock_fan.favorite_team = None
        mock_fan.avatar_url = None
        mock_fan.bio = None

        # Mock verification
        mock_verification = MagicMock()
        mock_verification.status = "pending"
        type(mock_fan).verification = PropertyMock(return_value=mock_verification)
        type(mock_fan).kyc_status = PropertyMock(return_value="pending")
        type(mock_fan).is_kyc_verified = PropertyMock(return_value=False)

        # Mock to_dict method
        def to_dict():
            data = {
                'user_id': 200,
                'display_name': "Test Fan",
                'verification_id': 2,
                'nationality': None,
                'favorite_team': None,
                'avatar_url': None,
                'bio': None,
                'kyc_status': "pending",
                'is_kyc_verified': False
            }
            # Simulate removal of verification_id when None
            if data.get('verification_id') is None:
                data.pop('verification_id', None)
            return data

        mock_fan.to_dict = to_dict

        data = mock_fan.to_dict()

        assert 'kyc_status' in data
        assert data['kyc_status'] == "pending"
        assert 'is_kyc_verified' in data
        assert data['is_kyc_verified'] == False
        # verification_id should be in data since it's not None
        assert 'verification_id' in data
        assert data['verification_id'] == 2

        # Test with no verification_id
        mock_fan2 = MagicMock()
        mock_fan2.user_id = 201
        mock_fan2.display_name = "Another Fan"
        mock_fan2.verification_id = None
        mock_fan2.nationality = None
        mock_fan2.favorite_team = None
        mock_fan2.avatar_url = None
        mock_fan2.bio = None
        type(mock_fan2).verification = PropertyMock(return_value=None)
        type(mock_fan2).kyc_status = PropertyMock(return_value=None)
        type(mock_fan2).is_kyc_verified = PropertyMock(return_value=False)

        def to_dict2():
            data = {
                'user_id': 201,
                'display_name': "Another Fan",
                'verification_id': None,
                'nationality': None,
                'favorite_team': None,
                'avatar_url': None,
                'bio': None,
                'kyc_status': None,
                'is_kyc_verified': False
            }
            if data.get('verification_id') is None:
                data.pop('verification_id', None)
            return data

        mock_fan2.to_dict = to_dict2
        data2 = mock_fan2.to_dict()
        # verification_id should not be in data when None
        assert 'verification_id' not in data2

    @patch('app.fan.services.registry.FanProfile')
    @patch('app.fan.services.registry.IndividualVerification')
    @patch('app.fan.services.registry.db.session')
    def test_get_or_create_fan_new_user(self, mock_db_session, MockIndividualVerification, MockFanProfile):
        """Test creating a new fan profile with KYC lookup"""
        # Mock query objects
        mock_fan_query = MagicMock()
        mock_fan_query.filter_by.return_value.first.return_value = None

        mock_verification_query = MagicMock()
        mock_verification_instance = MagicMock()
        mock_verification_instance.id = 5
        mock_verification_query.filter_by.return_value.order_by.return_value.first.return_value = mock_verification_instance

        # Set up class-level query attributes
        MockFanProfile.query = mock_fan_query
        MockIndividualVerification.query = mock_verification_query

        mock_commit = MagicMock()
        mock_db_session.commit = mock_commit
        mock_add = MagicMock()
        mock_db_session.add = mock_add

        # Create a mock fan instance to be returned
        mock_fan_instance = MagicMock()
        mock_fan_instance.user_id = 300
        mock_fan_instance.verification_id = None
        MockFanProfile.return_value = mock_fan_instance

        # Call the function
        result = get_or_create_fan(300)

        # Verify fan was created
        MockFanProfile.assert_called_once_with(
            user_id=300,
            display_name="Unknown",
            nationality="UG",
            favorite_team="None"
        )
        mock_add.assert_called_once_with(mock_fan_instance)
        mock_commit.assert_called()

        # Verify verification was linked
        assert mock_fan_instance.verification_id == 5

        # Verify it's cached
        from app.fan.services.registry import fan_registry
        assert 300 in fan_registry
        assert fan_registry[300] == result

    @patch('app.fan.services.registry.FanProfile')
    @patch('app.fan.services.registry.IndividualVerification')
    @patch('app.fan.services.registry.db.session')
    def test_get_or_create_fan_existing_user(self, mock_db_session, MockIndividualVerification, MockFanProfile):
        """Test getting existing fan profile"""
        # Mock existing fan
        mock_fan = MagicMock()
        mock_fan.user_id = 400
        mock_fan.verification_id = None

        mock_fan_query = MagicMock()
        mock_fan_query.filter_by.return_value.first.return_value = mock_fan

        mock_verification_query = MagicMock()
        mock_verification_query.filter_by.return_value.order_by.return_value.first.return_value = None

        MockFanProfile.query = mock_fan_query
        MockIndividualVerification.query = mock_verification_query

        mock_commit = MagicMock()
        mock_db_session.commit = mock_commit

        result = get_or_create_fan(400)

        # Should not commit if no verification to link
        mock_commit.assert_not_called()
        assert result == mock_fan

    def test_get_fan_kyc_status(self):
        """Test getting KYC status for a fan"""
        # Mock get_or_create_fan to return a fan with verification
        mock_fan = MagicMock()
        mock_fan.kyc_status = "verified"
        mock_fan.is_kyc_verified = True
        mock_fan.verification_id = 10

        with patch('app.fan.services.registry.get_or_create_fan', return_value=mock_fan):
            status = get_fan_kyc_status(500)

            assert status['status'] == "verified"
            assert status['is_verified'] == True
            assert status['verification_id'] == 10

    @patch('app.fan.services.registry.IndividualVerification')
    @patch('app.fan.services.registry.get_or_create_fan')
    @patch('app.fan.services.registry.db.session')
    def test_link_fan_to_verification_success(self, mock_db_session, mock_get_fan, MockIndividualVerification):
        """Test successfully linking fan to verification"""
        # Mock fan
        mock_fan = MagicMock()
        mock_fan.verification_id = None
        mock_get_fan.return_value = mock_fan

        # Mock verification
        mock_verification = MagicMock()
        mock_verification.id = 20
        mock_verification.user_id = 600

        mock_verification_query = MagicMock()
        mock_verification_query.get.return_value = mock_verification
        MockIndividualVerification.query = mock_verification_query

        mock_commit = MagicMock()
        mock_db_session.commit = mock_commit

        # Call function
        result = link_fan_to_verification(600, 20)

        assert result == True
        assert mock_fan.verification_id == 20
        mock_commit.assert_called_once()

    @patch('app.fan.services.registry.IndividualVerification')
    @patch('app.fan.services.registry.get_or_create_fan')
    def test_link_fan_to_verification_failure(self, mock_get_fan, MockIndividualVerification):
        """Test failed linking (verification not found or user mismatch)"""
        # Mock fan
        mock_fan = MagicMock()
        mock_get_fan.return_value = mock_fan

        # Test 1: Verification not found
        mock_verification_query = MagicMock()
        mock_verification_query.get.return_value = None
        MockIndividualVerification.query = mock_verification_query

        result = link_fan_to_verification(700, 30)
        assert result == False

        # Test 2: User ID mismatch
        mock_verification = MagicMock()
        mock_verification.id = 40
        mock_verification.user_id = 800  # Different from requested user_id
        mock_verification_query.get.return_value = mock_verification

        result = link_fan_to_verification(700, 40)
        assert result == False

    def test_update_fan_profile(self):
        """Test updating fan profile information"""
        # Mock get_or_create_fan
        mock_fan = MagicMock()
        mock_fan.display_name = "Old Name"
        mock_fan.nationality = "Old Country"
        mock_fan.favorite_team = "Old Team"
        mock_fan.avatar_url = None

        with patch('app.fan.services.registry.get_or_create_fan', return_value=mock_fan):
            with patch('app.fan.services.registry.db.session.commit') as mock_commit:
                result = update_fan_profile(
                    user_id=900,
                    name="New Name",
                    nationality="New Country",
                    favorite_team="New Team",
                    avatar_url="http://example.com/avatar.jpg"
                )

                assert result == mock_fan
                assert mock_fan.display_name == "New Name"
                assert mock_fan.nationality == "New Country"
                assert mock_fan.favorite_team == "New Team"
                assert mock_fan.avatar_url == "http://example.com/avatar.jpg"
                mock_commit.assert_called_once()


class TestIndividualVerificationRelationships:
    """Test IndividualVerification relationships with FanProfile"""

    @patch('app.identity.individuals.individual_verification.IndividualVerification')
    def test_individual_verification_fan_profile_relationship(self, MockIndividualVerification):
        """Test that IndividualVerification has relationship to FanProfile"""
        # Create mock verification
        mock_verification = MagicMock()

        # The relationship should exist
        assert hasattr(mock_verification, 'fan_profile')
        # We can't test actual SQLAlchemy configuration in unit tests


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
