"""
Tests for Bank of Uganda compliant KYC tier system.
"""

import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal
from datetime import datetime, timezone

from app.auth.kyc_compliance import (
    calculate_kyc_tier, get_user_limits, check_transaction_allowed,
    TIER_0_UNREGISTERED, TIER_1_BASIC, TIER_2_STANDARD,
    TIER_3_ENHANCED, TIER_4_PREMIUM, TIER_5_CORPORATE,
    require_kyc_tier, require_kyc_tier_for_amount
)


class TestKYCCompliance:
    """Test KYC compliance logic."""

    @patch('app.auth.kyc_compliance.is_requirement_enabled', return_value=True)
    @patch('app.kyc.models.KycRecord')
    @patch('app.auth.kyc_compliance.db')
    @patch('app.auth.kyc_compliance.get_profile_by_user', return_value=None)
    @patch('app.auth.kyc_compliance.IndividualVerification')
    def test_calculate_kyc_tier_tier0(self, MockVerification, mock_profile, mock_db, MockKycRecord, mock_req):
        """Test tier 0 calculation (unregistered, no phone)."""
        mock_user = MagicMock()
        mock_user.public_id = 'test-public-id'
        mock_user.phone_verified = False
        mock_user.phone_verified_at = None
        mock_user.phone = None
        mock_db.session.get.return_value = mock_user
        MockVerification.query.filter_by.return_value.order_by.return_value.first.return_value = None
        MockKycRecord.query.filter_by.return_value.order_by.return_value.first.return_value = None
        MockKycRecord.query.filter_by.return_value.all.return_value = []

        result = calculate_kyc_tier(1)

        assert result["tier"] == TIER_0_UNREGISTERED
        assert "phone_verified" in result["missing_requirements"]

    @patch('app.auth.kyc_compliance.is_requirement_enabled', return_value=True)
    @patch('app.kyc.models.KycRecord')
    @patch('app.auth.kyc_compliance.db')
    @patch('app.auth.kyc_compliance.get_profile_by_user', return_value=None)
    @patch('app.auth.kyc_compliance.IndividualVerification')
    def test_calculate_kyc_tier_tier1(self, MockVerification, mock_profile, mock_db, MockKycRecord, mock_req):
        """Test tier 1 calculation (basic, phone only)."""
        mock_user = MagicMock()
        mock_user.public_id = 'test-public-id'
        mock_user.phone_verified = True
        mock_user.phone_verified_at = datetime.now(timezone.utc)
        mock_user.phone = '+256700000000'
        mock_db.session.get.return_value = mock_user
        MockVerification.query.filter_by.return_value.order_by.return_value.first.return_value = None
        MockKycRecord.query.filter_by.return_value.order_by.return_value.first.return_value = None
        MockKycRecord.query.filter_by.return_value.all.return_value = []

        result = calculate_kyc_tier(1)

        assert result["tier"] == TIER_1_BASIC
        assert result["tier_name"] == "Basic"

    @patch('app.auth.kyc_compliance.is_requirement_enabled', return_value=True)
    @patch('app.kyc.models.KycRecord')
    @patch('app.auth.kyc_compliance.db')
    @patch('app.auth.kyc_compliance.get_profile_by_user', return_value=None)
    @patch('app.auth.kyc_compliance.IndividualVerification')
    def test_calculate_kyc_tier_tier2(self, MockVerification, mock_profile, mock_db, MockKycRecord, mock_req):
        """Test tier 2 calculation (standard, national_id + biometric)."""
        mock_user = MagicMock()
        mock_user.public_id = 'test-public-id'
        mock_user.phone_verified = True
        mock_user.phone_verified_at = datetime.now(timezone.utc)
        mock_user.phone = '+256700000000'
        mock_db.session.get.return_value = mock_user
        mock_verification = MagicMock()
        mock_verification.status = "verified"
        mock_verification.scope = {"national_id": True, "biometric": True}
        MockVerification.query.filter_by.return_value.order_by.return_value.first.return_value = mock_verification
        MockKycRecord.query.filter_by.return_value.order_by.return_value.first.return_value = None
        MockKycRecord.query.filter_by.return_value.all.return_value = []

        result = calculate_kyc_tier(1)

        assert result["tier"] == TIER_2_STANDARD
        assert result["tier_name"] == "Standard"

    @patch('app.auth.kyc_compliance.is_requirement_enabled', return_value=True)
    @patch('app.kyc.models.KycRecord')
    @patch('app.auth.kyc_compliance.db')
    @patch('app.auth.kyc_compliance.get_profile_by_user', return_value=None)
    @patch('app.auth.kyc_compliance.IndividualVerification')
    def test_calculate_kyc_tier_tier3(self, MockVerification, mock_profile, mock_db, MockKycRecord, mock_req):
        """Test tier 3 calculation (enhanced, full scope)."""
        mock_user = MagicMock()
        mock_user.public_id = 'test-public-id'
        mock_user.phone_verified = True
        mock_user.phone_verified_at = datetime.now(timezone.utc)
        mock_user.phone = '+256700000000'
        mock_db.session.get.return_value = mock_user
        mock_verification = MagicMock()
        mock_verification.status = "verified"
        mock_verification.scope = {
            "national_id": True,
            "biometric": True,
            "address": True,
            "tax": True
        }
        MockVerification.query.filter_by.return_value.order_by.return_value.first.return_value = mock_verification
        MockKycRecord.query.filter_by.return_value.order_by.return_value.first.return_value = None
        MockKycRecord.query.filter_by.return_value.all.return_value = []

        result = calculate_kyc_tier(1)

        assert result["tier"] == TIER_3_ENHANCED
        assert result["tier_name"] == "Enhanced"

    def test_get_user_limits(self):
        """Test getting user limits (no wallet TRANSACTION model available in context)."""
        from flask import Flask
        import builtins
        app = Flask(__name__)

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            # Force the usage-lookup branch to fall back to zero usage.
            if name == 'app.wallet.models.transaction':
                raise ImportError('Mock import error')
            return original_import(name, *args, **kwargs)

        with app.app_context():
            with patch('app.auth.kyc_compliance.db.session.get') as mock_get, \
                 patch('app.auth.kyc_compliance.calculate_kyc_tier') as mock_calc, \
                 patch('builtins.__import__', side_effect=mock_import):
                mock_user = MagicMock()
                mock_user.public_id = 'test-public-id'
                mock_get.return_value = mock_user
                mock_calc.return_value = {
                    "tier": TIER_2_STANDARD,
                    "tier_name": "Standard",
                    "limits": {
                        "daily": 2000000,
                        "monthly": 10000000,
                        "transaction": 500000
                    }
                }

                limits = get_user_limits(1)

                assert limits["daily"] == 2000000
                assert limits["daily_used"] == 0
                assert limits["daily_remaining"] == 2000000
                assert limits["monthly"] == 10000000
                assert limits["monthly_used"] == 0
                assert limits["monthly_remaining"] == 10000000

    @patch('app.auth.kyc_compliance.calculate_kyc_tier')
    @patch('app.auth.kyc_compliance.get_user_limits')
    @patch('app.auth.kyc_compliance.db.session.get')
    def test_check_transaction_allowed(self, mock_db_get, mock_get_limits, mock_calc_tier):
        """Test transaction allowance checking."""
        from app.identity.models.user import User
        
        # Setup mock user
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_db_get.return_value = mock_user
        
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
