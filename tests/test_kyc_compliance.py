"""
Tests for Bank of Uganda compliant KYC tier system.
"""

import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

from app.auth.kyc_compliance import (
    calculate_kyc_tier, get_user_limits, check_transaction_allowed,
    TIER_0_UNREGISTERED, TIER_1_BASIC, TIER_2_STANDARD,
    TIER_3_ENHANCED, TIER_4_PREMIUM, TIER_5_CORPORATE,
    require_kyc_tier, require_kyc_tier_for_amount
)


class TestKYCCompliance:
    """Test KYC compliance logic."""

    @patch('app.auth.kyc_compliance.UserProfile')
    @patch('app.auth.kyc_compliance.IndividualVerification')
    def test_calculate_kyc_tier_tier0(self, MockVerification, MockUserProfile):
        """Test tier 0 calculation (unregistered)."""
        # Mock user without phone verification
        mock_profile = MagicMock()
        mock_profile.phone_number = None
        mock_profile.phone_verified = False
        MockUserProfile.query.filter_by.return_value.first.return_value = mock_profile

        result = calculate_kyc_tier(1)

        assert result["tier"] == TIER_0_UNREGISTERED
        assert "phone_verified" in result["missing_requirements"]

    @patch('app.auth.kyc_compliance.UserProfile')
    @patch('app.auth.kyc_compliance.IndividualVerification')
    def test_calculate_kyc_tier_tier1(self, MockVerification, MockUserProfile):
        """Test tier 1 calculation (basic)."""
        # Mock user with phone verification only
        mock_profile = MagicMock()
        mock_profile.phone_number = "+256700000000"
        mock_profile.phone_verified = True
        MockUserProfile.query.filter_by.return_value.first.return_value = mock_profile

        # Mock no verification record
        MockVerification.query.filter_by.return_value.order_by.return_value.first.return_value = None

        result = calculate_kyc_tier(1)

        assert result["tier"] == TIER_1_BASIC
        assert result["tier_name"] == "Basic"

    @patch('app.auth.kyc_compliance.UserProfile')
    @patch('app.auth.kyc_compliance.IndividualVerification')
    def test_calculate_kyc_tier_tier2(self, MockVerification, MockUserProfile):
        """Test tier 2 calculation (standard)."""
        # Mock user with phone verification
        mock_profile = MagicMock()
        mock_profile.phone_number = "+256700000000"
        mock_profile.phone_verified = True
        MockUserProfile.query.filter_by.return_value.first.return_value = mock_profile

        # Mock verification with national ID and biometric
        mock_verification = MagicMock()
        mock_verification.status = "verified"
        mock_verification.scope = {"national_id": True, "biometric": True}
        MockVerification.query.filter_by.return_value.order_by.return_value.first.return_value = mock_verification

        result = calculate_kyc_tier(1)

        assert result["tier"] == TIER_2_STANDARD
        assert result["tier_name"] == "Standard"

    @patch('app.auth.kyc_compliance.UserProfile')
    @patch('app.auth.kyc_compliance.IndividualVerification')
    def test_calculate_kyc_tier_tier3(self, MockVerification, MockUserProfile):
        """Test tier 3 calculation (enhanced)."""
        # Mock user with phone verification
        mock_profile = MagicMock()
        mock_profile.phone_number = "+256700000000"
        mock_profile.phone_verified = True
        MockUserProfile.query.filter_by.return_value.first.return_value = mock_profile

        # Mock verification with all tier 3 requirements
        mock_verification = MagicMock()
        mock_verification.status = "verified"
        mock_verification.scope = {
            "national_id": True,
            "biometric": True,
            "address": True,
            "tax": True
        }
        MockVerification.query.filter_by.return_value.order_by.return_value.first.return_value = mock_verification

        result = calculate_kyc_tier(1)

        assert result["tier"] == TIER_3_ENHANCED
        assert result["tier_name"] == "Enhanced"

    def test_get_user_limits(self):
        """Test getting user limits."""
        # Create a Flask app context
        from flask import Flask
        app = Flask(__name__)

        with app.app_context():
            # Mock calculate_kyc_tier
            with patch('app.auth.kyc_compliance.calculate_kyc_tier') as mock_calc:
                mock_calc.return_value = {
                    "tier": TIER_2_STANDARD,
                    "tier_name": "Standard",
                    "limits": {
                        "daily": 2000000,
                        "monthly": 10000000,
                        "transaction": 500000
                    }
                }

                # Mock builtins.__import__ to raise ImportError for wallet models
                import builtins
                original_import = builtins.__import__

                def mock_import(name, *args, **kwargs):
                    if name == 'app.wallet.models':
                        raise ImportError('Mock import error')
                    return original_import(name, *args, **kwargs)

                with patch('builtins.__import__', side_effect=mock_import):
                    limits = get_user_limits(1)

                    # Check returned values (defaults from except block)
                    assert limits["daily"] == 2000000
                    assert limits["daily_used"] == 0
                    assert limits["daily_remaining"] == 2000000
                    assert limits["monthly"] == 10000000
                    assert limits["monthly_used"] == 0
                    assert limits["monthly_remaining"] == 10000000

    @patch('app.auth.kyc_compliance.calculate_kyc_tier')
    @patch('app.auth.kyc_compliance.get_user_limits')
    def test_check_transaction_allowed(self, mock_get_limits, mock_calc_tier):
        """Test transaction allowance checking."""
        # Setup tier 2 user
        mock_calc_tier.return_value = {
            "tier": TIER_2_STANDARD,
            "limits": {"transaction": 500000}
        }

        mock_get_limits.return_value = {
            "daily_remaining": 1500000,
            "monthly_remaining": 9500000
        }

        # Test allowed transaction
        allowed, reason = check_transaction_allowed(1, 300000)
        assert allowed == True
        assert "allowed" in reason.lower()

        # Test transaction exceeding limit
        allowed, reason = check_transaction_allowed(1, 600000)
        assert allowed == False
        assert "exceeds" in reason.lower()

    def test_require_kyc_tier_decorator(self):
        """Test KYC tier decorator."""
        # This is a basic test - actual decorator testing requires Flask context
        decorator = require_kyc_tier(TIER_2_STANDARD)
        assert callable(decorator)

    def test_require_kyc_tier_for_amount_decorator(self):
        """Test amount-based KYC tier decorator."""
        decorator = require_kyc_tier_for_amount('amount')
        assert callable(decorator)


class TestKYCLimits:
    """Test KYC limit enforcement."""

    def test_tier_limits(self):
        """Verify tier limits match BoU guidelines."""
        from app.auth.kyc_compliance import DAILY_LIMITS, MONTHLY_LIMITS, TRANSACTION_LIMITS

        assert DAILY_LIMITS[TIER_1_BASIC] == 400000
        assert DAILY_LIMITS[TIER_2_STANDARD] == 2000000
        assert DAILY_LIMITS[TIER_3_ENHANCED] == 7000000
        assert DAILY_LIMITS[TIER_4_PREMIUM] == 20000000

        assert MONTHLY_LIMITS[TIER_1_BASIC] == 2000000
        assert MONTHLY_LIMITS[TIER_2_STANDARD] == 10000000
        assert MONTHLY_LIMITS[TIER_3_ENHANCED] == 35000000

        assert TRANSACTION_LIMITS[TIER_1_BASIC] == 100000
        assert TRANSACTION_LIMITS[TIER_2_STANDARD] == 500000
        assert TRANSACTION_LIMITS[TIER_3_ENHANCED] == 2000000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
