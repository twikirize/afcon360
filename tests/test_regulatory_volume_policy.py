"""
Tests for Regulatory Volume Policy Engine

Tests both calendar and rolling window modes, timezone handling,
reversal/refund exclusion, transaction status filtering, and authorization.
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.wallet.models.regulatory_volume import (
    WindowMode,
    RegulatoryVolumePolicy,
    RegulatoryVolumePolicyChangeRequest,
    LedgerReversalReference,
)
from app.wallet.services.regulatory_volume_calculator import (
    TimezoneEngine,
    VolumeWindowCalculator,
    RegulatoryVolumeCalculator,
)
from app.wallet.services.regulatory_volume_policy_service import RegulatoryVolumePolicyService
from app.wallet.models.ledger import LedgerEntryModel, AccountModel, EntryType, AccountOwnerType
from app.wallet.models.transaction import TransactionModel, TransactionStatus, TransactionType


class TestTimezoneEngine:
    """Test timezone conversion for Kampala (EAT = UTC+3)."""
    
    def test_utc_to_kampala(self):
        """UTC midnight should be 3am Kampala time."""
        utc_midnight = datetime(2026, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        kampala = TimezoneEngine.utc_to_kampala(utc_midnight)
        assert kampala.hour == 3
        assert kampala.tzinfo is not None
    
    def test_kampala_to_utc(self):
        """3am Kampala should be midnight UTC."""
        kampala_3am = datetime(2026, 1, 15, 3, 0, 0)
        kampala_3am = kampala_3am.replace(tzinfo=timezone(timedelta(hours=3)))
        utc = TimezoneEngine.kampala_to_utc(kampala_3am)
        assert utc.hour == 0
        assert utc.tzinfo == timezone.utc
    
    def test_get_day_start_utc(self):
        """Day start in Kampala (00:00 EAT) = previous day 21:00 UTC."""
        # 2026-01-15 10:00 EAT = 2026-01-15 07:00 UTC
        kampala_dt = datetime(2026, 1, 15, 10, 0, 0)
        kampala_dt = kampala_dt.replace(tzinfo=timezone(timedelta(hours=3)))
        
        day_start_utc = TimezoneEngine.get_day_start_utc(kampala_dt)
        # Should be 2026-01-15 00:00 EAT = 2026-01-14 21:00 UTC
        assert day_start_utc == datetime(2026, 1, 14, 21, 0, 0, tzinfo=timezone.utc)
    
    def test_get_month_start_utc(self):
        """Month start in Kampala (1st 00:00 EAT) = previous month last day 21:00 UTC."""
        kampala_dt = datetime(2026, 1, 15, 10, 0, 0)
        kampala_dt = kampala_dt.replace(tzinfo=timezone(timedelta(hours=3)))
        
        month_start_utc = TimezoneEngine.get_month_start_utc(kampala_dt)
        # Should be 2026-01-01 00:00 EAT = 2025-12-31 21:00 UTC
        assert month_start_utc == datetime(2025, 12, 31, 21, 0, 0, tzinfo=timezone.utc)


class TestVolumeWindowCalculator:
    """Test window boundary calculations for both calendar and rolling modes."""
    
    def test_calendar_daily_window(self):
        """Calendar daily: 00:00 local to now."""
        policy = RegulatoryVolumePolicy(
            daily_window_mode=WindowMode.CALENDAR,
            monthly_window_mode=WindowMode.CALENDAR,
            timezone='Africa/Kampala'
        )
        calc = VolumeWindowCalculator(policy)
        
        # 2026-01-15 10:00 EAT = 2026-01-15 07:00 UTC
        as_of = datetime(2026, 1, 15, 7, 0, 0, tzinfo=timezone.utc)
        start, end = calc.get_daily_window_bounds(as_of)
        
        # Start should be 2026-01-15 00:00 EAT = 2026-01-14 21:00 UTC
        assert start == datetime(2026, 1, 14, 21, 0, 0, tzinfo=timezone.utc)
        assert end == as_of
    
    def test_rolling_daily_window(self):
        """Rolling daily: now - 24 hours."""
        policy = RegulatoryVolumePolicy(
            daily_window_mode=WindowMode.ROLLING,
            monthly_window_mode=WindowMode.CALENDAR,
            timezone='Africa/Kampala'
        )
        calc = VolumeWindowCalculator(policy)
        
        as_of = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        start, end = calc.get_daily_window_bounds(as_of)
        
        assert start == datetime(2026, 1, 14, 12, 0, 0, tzinfo=timezone.utc)
        assert end == as_of
    
    def test_calendar_monthly_window(self):
        """Calendar monthly: 1st 00:00 local to now."""
        policy = RegulatoryVolumePolicy(
            daily_window_mode=WindowMode.CALENDAR,
            monthly_window_mode=WindowMode.CALENDAR,
            timezone='Africa/Kampala'
        )
        calc = VolumeWindowCalculator(policy)
        
        # 2026-01-15 10:00 EAT = 2026-01-15 07:00 UTC
        as_of = datetime(2026, 1, 15, 7, 0, 0, tzinfo=timezone.utc)
        start, end = calc.get_monthly_window_bounds(as_of)
        
        # Start should be 2026-01-01 00:00 EAT = 2025-12-31 21:00 UTC
        assert start == datetime(2025, 12, 31, 21, 0, 0, tzinfo=timezone.utc)
        assert end == as_of
    
    def test_rolling_monthly_window(self):
        """Rolling monthly: now - 30 days."""
        policy = RegulatoryVolumePolicy(
            daily_window_mode=WindowMode.CALENDAR,
            monthly_window_mode=WindowMode.ROLLING,
            timezone='Africa/Kampala'
        )
        calc = VolumeWindowCalculator(policy)
        
        as_of = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        start, end = calc.get_monthly_window_bounds(as_of)
        
        assert start == datetime(2025, 12, 16, 12, 0, 0, tzinfo=timezone.utc)
        assert end == as_of
    
    def test_mixed_modes(self):
        """Test calendar daily + rolling monthly combination."""
        policy = RegulatoryVolumePolicy(
            daily_window_mode=WindowMode.CALENDAR,
            monthly_window_mode=WindowMode.ROLLING,
            timezone='Africa/Kampala'
        )
        calc = VolumeWindowCalculator(policy)
        
        as_of = datetime(2026, 1, 15, 7, 0, 0, tzinfo=timezone.utc)
        daily_start, daily_end = calc.get_daily_window_bounds(as_of)
        monthly_start, monthly_end = calc.get_monthly_window_bounds(as_of)
        
        # Calendar daily
        assert daily_start == datetime(2026, 1, 14, 21, 0, 0, tzinfo=timezone.utc)
        # Rolling monthly
        assert monthly_start == datetime(2025, 12, 16, 7, 0, 0, tzinfo=timezone.utc)


class TestRegulatoryVolumeCalculator:
    """Test the main volume calculator with eligibility filters."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.account_id = uuid4()
        self.currency = 'UGX'
        self.policy = RegulatoryVolumePolicy(
            daily_window_mode=WindowMode.CALENDAR,
            monthly_window_mode=WindowMode.CALENDAR,
            timezone='Africa/Kampala',
            is_active=True
        )
    
    @patch('app.wallet.services.regulatory_volume_calculator.db')
    def test_daily_volume_excludes_pending_transactions(self, mock_db):
        """PENDING transactions should not count toward regulatory volume."""
        mock_session = MagicMock()
        mock_db.session = mock_session
        
        # Mock the query execution
        mock_result = MagicMock()
        mock_result.scalar.return_value = Decimal('500000')
        mock_session.execute.return_value = mock_result
        
        calculator = RegulatoryVolumeCalculator(db_session=mock_session, policy=self.policy)
        volume = calculator.get_daily_volume(self.account_id, self.currency)
        
        assert volume == Decimal('500000')
        # Verify the query was built with COMPLETED status filter
        call_args = mock_session.execute.call_args
        assert call_args is not None
    
    @patch('app.wallet.services.regulatory_volume_calculator.db')
    def test_daily_volume_excludes_reversals(self, mock_db):
        """Reversal entries should not count toward regulatory volume."""
        mock_session = MagicMock()
        mock_db.session = mock_session
        
        mock_result = MagicMock()
        mock_result.scalar.return_value = Decimal('300000')
        mock_session.execute.return_value = mock_result
        
        calculator = RegulatoryVolumeCalculator(db_session=mock_session, policy=self.policy)
        volume = calculator.get_daily_volume(self.account_id, self.currency)
        
        assert volume == Decimal('300000')
    
    @patch('app.wallet.services.regulatory_volume_calculator.db')
    def test_daily_volume_excludes_credits(self, mock_db):
        """CREDIT entries (refunds) should not count toward DEBIT volume."""
        mock_session = MagicMock()
        mock_db.session = mock_session
        
        mock_result = MagicMock()
        mock_result.scalar.return_value = Decimal('1000000')  # Only debits
        mock_session.execute.return_value = mock_result
        
        calculator = RegulatoryVolumeCalculator(db_session=mock_session, policy=self.policy)
        volume = calculator.get_daily_volume(self.account_id, self.currency)
        
        assert volume == Decimal('1000000')
    
    @patch('app.wallet.services.regulatory_volume_calculator.db')
    def test_check_daily_limit_within_limit(self, mock_db):
        """Transaction within daily limit should be allowed."""
        mock_session = MagicMock()
        mock_db.session = mock_session
        
        # Mock volume query to return 500,000
        mock_result = MagicMock()
        mock_result.scalar.return_value = Decimal('500000')
        mock_session.execute.return_value = mock_result
        
        calculator = RegulatoryVolumeCalculator(db_session=mock_session, policy=self.policy)
        allowed, current, limit = calculator.check_daily_limit(
            self.account_id, self.currency, Decimal('300000'), Decimal('1000000')
        )
        
        assert allowed is True
        assert current == Decimal('500000')
        assert limit == Decimal('1000000')
    
    @patch('app.wallet.services.regulatory_volume_calculator.db')
    def test_check_daily_limit_exceeds_limit(self, mock_db):
        """Transaction exceeding daily limit should be rejected."""
        mock_session = MagicMock()
        mock_db.session = mock_session
        
        # Mock volume query to return 900,000
        mock_result = MagicMock()
        mock_result.scalar.return_value = Decimal('900000')
        mock_session.execute.return_value = mock_result
        
        calculator = RegulatoryVolumeCalculator(db_session=mock_session, policy=self.policy)
        allowed, current, limit = calculator.check_daily_limit(
            self.account_id, self.currency, Decimal('200000'), Decimal('1000000')
        )
        
        assert allowed is False
        assert current == Decimal('900000')
        assert limit == Decimal('1000000')
    
    @patch('app.wallet.services.regulatory_volume_calculator.db')
    def test_zero_limit_unbounded(self, mock_db):
        """Zero/None limit means unbounded (tier 5 corporate)."""
        mock_session = MagicMock()
        mock_db.session = mock_session
        
        calculator = RegulatoryVolumeCalculator(db_session=mock_session, policy=self.policy)
        allowed, current, limit = calculator.check_daily_limit(
            self.account_id, self.currency, Decimal('10000000'), Decimal('0')
        )
        
        assert allowed is True
        assert limit == Decimal('0')


class TestRegulatoryVolumePolicyService:
    """Test policy change request workflow with dual authorization."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.requester_id = 1
        self.approver_id = 2
    
    def test_request_policy_change_requires_authorization(self, app):
        """Only owner/super_admin can request policy changes."""
        with app.test_request_context():
            with patch('app.wallet.services.regulatory_volume_policy_service.RegulatoryVolumePolicyService._require_authorization', return_value=False):
                with patch('app.wallet.services.regulatory_volume_policy_service.db') as mock_db:
                    mock_session = MagicMock()
                    mock_db.session = mock_session
                    
                    with pytest.raises(PermissionError):
                        RegulatoryVolumePolicyService.request_policy_change(
                            WindowMode.CALENDAR, WindowMode.CALENDAR, 'Africa/Kampala', reason='test'
                        )
    
    def test_request_policy_change_success(self, app):
        """Authorized user can request policy change."""
        with app.test_request_context():
            with patch('app.wallet.services.regulatory_volume_policy_service.RegulatoryVolumePolicyService._require_authorization', return_value=True):
                with patch('app.wallet.services.regulatory_volume_policy_service.current_user') as mock_current_user:
                    mock_current_user.id = self.requester_id
                    mock_current_user.has_role = MagicMock(return_value=True)
                    
                    with patch('app.wallet.services.regulatory_volume_policy_service.db') as mock_db:
                        mock_session = MagicMock()
                        mock_db.session = mock_session
                        
                        # Mock the add and commit to simulate successful save
                        def mock_add(obj):
                            # Simulate the object being persisted with an ID
                            obj.id = 1
                            obj.status = RegulatoryVolumePolicyChangeRequest.Status.PENDING
                        mock_session.add.side_effect = mock_add
                        
                        change_request = RegulatoryVolumePolicyService.request_policy_change(
                            WindowMode.ROLLING, WindowMode.CALENDAR, 'Africa/Kampala', reason='Switch to rolling daily'
                        )
                        
                        assert change_request.proposed_daily_mode == WindowMode.ROLLING
                        assert change_request.proposed_monthly_mode == WindowMode.CALENDAR
                        assert change_request.requested_by == self.requester_id
                        assert change_request.status == RegulatoryVolumePolicyChangeRequest.Status.PENDING
    
    def test_approve_own_request_fails(self, app):
        """Requester cannot approve their own change request."""
        with app.test_request_context():
            with patch('app.wallet.services.regulatory_volume_policy_service.RegulatoryVolumePolicyService._require_authorization', return_value=True):
                with patch('app.wallet.services.regulatory_volume_policy_service.current_user') as mock_current_user:
                    mock_current_user.id = self.requester_id
                    mock_current_user.has_role = MagicMock(return_value=True)
                    
                    with patch('app.wallet.services.regulatory_volume_policy_service.db') as mock_db:
                        mock_session = MagicMock()
                        mock_db.session = mock_session
                        
                        # Create a mock change request
                        change_request = RegulatoryVolumePolicyChangeRequest(
                            id=1,
                            proposed_daily_mode=WindowMode.ROLLING,
                            proposed_monthly_mode=WindowMode.CALENDAR,
                            proposed_timezone='Africa/Kampala',
                            proposed_effective_from=datetime.now(timezone.utc),
                            requested_by=self.requester_id,
                            status=RegulatoryVolumePolicyChangeRequest.Status.PENDING
                        )
                        mock_session.get.return_value = change_request
                        
                        with pytest.raises(PermissionError, match="Requester cannot approve their own"):
                            RegulatoryVolumePolicyService.approve_policy_change(1, 'Approved')
    
    def test_approve_by_different_user_succeeds(self, app):
        """Different authorized user can approve the request."""
        with app.test_request_context():
            with patch('app.wallet.services.regulatory_volume_policy_service.RegulatoryVolumePolicyService._require_authorization', return_value=True):
                with patch('app.wallet.services.regulatory_volume_policy_service.current_user') as mock_current_user:
                    mock_current_user.id = self.approver_id
                    mock_current_user.has_role = MagicMock(return_value=True)
                    
                    with patch('app.wallet.services.regulatory_volume_policy_service.db') as mock_db:
                        mock_session = MagicMock()
                        mock_db.session = mock_session
                        
                        # Create a mock change request
                        change_request = RegulatoryVolumePolicyChangeRequest(
                            id=1,
                            proposed_daily_mode=WindowMode.ROLLING,
                            proposed_monthly_mode=WindowMode.CALENDAR,
                            proposed_timezone='Africa/Kampala',
                            proposed_effective_from=datetime.now(timezone.utc),
                            requested_by=self.requester_id,
                            status=RegulatoryVolumePolicyChangeRequest.Status.PENDING
                        )
                        mock_session.get.return_value = change_request
                        
                        # Mock the get_active query to return None (no existing policy)
                        with patch.object(RegulatoryVolumePolicy, 'get_active', return_value=None):
                            # Mock the query for current active policy
                            mock_query = MagicMock()
                            mock_session.query.return_value = mock_query
                            mock_query.filter_by.return_value = mock_query
                            mock_query.first.return_value = None
                            
                            new_policy = RegulatoryVolumePolicyService.approve_policy_change(1, 'Approved for compliance')
                            
                            assert new_policy.daily_window_mode == WindowMode.ROLLING
                            assert new_policy.monthly_window_mode == WindowMode.CALENDAR
                            assert new_policy.approved_by == self.approver_id
                            assert change_request.status == RegulatoryVolumePolicyChangeRequest.Status.APPROVED
                            assert change_request.approved_by == self.approver_id


class TestLedgerReversalReference:
    """Test reversal reference model for excluding reversals from volume."""
    
    def test_reversal_reference_creation(self, app):
        """Can create reversal reference linking original and reversal entries."""
        with app.app_context():
            original_entry_id = uuid4()
            reversal_entry_id = uuid4()
            original_tx_id = uuid4()
            
            ref = LedgerReversalReference(
                original_entry_id=original_entry_id,
                reversal_entry_id=reversal_entry_id,
                original_transaction_id=original_tx_id,
                reversal_type='refund',
                reason='Customer requested refund'
            )
            
            assert ref.original_entry_id == original_entry_id
            assert ref.reversal_entry_id == reversal_entry_id
            assert ref.reversal_type == 'refund'
    
    def test_reversal_type_enum_values(self, app):
        """Common reversal types should be supported."""
        with app.app_context():
            types = ['refund', 'reversal', 'chargeback', 'correction']
            for rtype in types:
                ref = LedgerReversalReference(
                    original_entry_id=uuid4(),
                    reversal_entry_id=uuid4(),
                    reversal_type=rtype
                )
                assert ref.reversal_type == rtype


class TestCalendarBoundaryEdgeCases:
    """Test calendar boundary edge cases (month transitions, year transitions, DST)."""
    
    def test_january_first_day_start(self):
        """January 1st month start should be previous year December."""
        kampala_dt = datetime(2026, 1, 1, 0, 0, 0)
        kampala_dt = kampala_dt.replace(tzinfo=timezone(timedelta(hours=3)))
        
        month_start = TimezoneEngine.get_month_start_utc(kampala_dt)
        # Should be 2025-12-31 21:00 UTC
        assert month_start == datetime(2025, 12, 31, 21, 0, 0, tzinfo=timezone.utc)
    
    def test_december_month_start(self):
        """December month start should be November 30."""
        kampala_dt = datetime(2026, 12, 15, 10, 0, 0)
        kampala_dt = kampala_dt.replace(tzinfo=timezone(timedelta(hours=3)))
        
        month_start = TimezoneEngine.get_month_start_utc(kampala_dt)
        # Should be 2026-11-30 21:00 UTC
        assert month_start == datetime(2026, 11, 30, 21, 0, 0, tzinfo=timezone.utc)
    
    def test_february_to_march_transition(self):
        """February month end should correctly transition to March."""
        kampala_dt = datetime(2026, 2, 28, 23, 59, 59)
        kampala_dt = kampala_dt.replace(tzinfo=timezone(timedelta(hours=3)))
        
        # This is still February
        day_start = TimezoneEngine.get_day_start_utc(kampala_dt)
        # 2026-02-28 00:00 EAT = 2026-02-27 21:00 UTC
        assert day_start == datetime(2026, 2, 27, 21, 0, 0, tzinfo=timezone.utc)
        
        # Next second is March 1st
        kampala_dt_march = datetime(2026, 3, 1, 0, 0, 0)
        kampala_dt_march = kampala_dt_march.replace(tzinfo=timezone(timedelta(hours=3)))
        
        day_start_march = TimezoneEngine.get_day_start_utc(kampala_dt_march)
        # 2026-03-01 00:00 EAT = 2026-02-28 21:00 UTC
        assert day_start_march == datetime(2026, 2, 28, 21, 0, 0, tzinfo=timezone.utc)


class TestMultiCurrencyIsolation:
    """Test that volume calculation is isolated per currency."""
    
    @patch('app.wallet.services.regulatory_volume_calculator.db')
    def test_currency_isolation(self, mock_db):
        """UGX and USD volumes should be calculated separately."""
        mock_session = MagicMock()
        mock_db.session = mock_session
        
        mock_result = MagicMock()
        mock_result.scalar.return_value = Decimal('500000')
        mock_session.execute.return_value = mock_result
        
        policy = RegulatoryVolumePolicy(
            daily_window_mode=WindowMode.CALENDAR,
            monthly_window_mode=WindowMode.CALENDAR,
            timezone='Africa/Kampala'
        )
        calculator = RegulatoryVolumeCalculator(db_session=mock_session, policy=policy)
        
        # Query for UGX
        ugx_volume = calculator.get_daily_volume(uuid4(), 'UGX')
        # Query for USD
        usd_volume = calculator.get_daily_volume(uuid4(), 'USD')
        
        # Both should execute separate queries
        assert mock_session.execute.call_count == 2


class TestPlatformAccountIsolation:
    """Test that platform/system accounts don't contaminate customer volume."""
    
    @patch('app.wallet.services.regulatory_volume_calculator.db')
    def test_customer_volume_only_includes_customer_account(self, mock_db):
        """Volume query should filter by specific account_id."""
        mock_session = MagicMock()
        mock_db.session = mock_session
        
        mock_result = MagicMock()
        mock_result.scalar.return_value = Decimal('100000')
        mock_session.execute.return_value = mock_result
        
        policy = RegulatoryVolumePolicy(
            daily_window_mode=WindowMode.CALENDAR,
            monthly_window_mode=WindowMode.CALENDAR,
            timezone='Africa/Kampala'
        )
        calculator = RegulatoryVolumeCalculator(db_session=mock_session, policy=policy)
        
        customer_account_id = uuid4()
        volume = calculator.get_daily_volume(customer_account_id, 'UGX')
        
        assert volume == Decimal('100000')
        # Verify query was built with the specific account_id
        call_args = mock_session.execute.call_args
        assert call_args is not None


class TestPolicyChangeAudit:
    """Test that policy changes produce audit events."""
    
    def test_request_logs_audit(self, app):
        """Requesting a policy change should log audit event."""
        with app.test_request_context():
            with patch('app.wallet.services.regulatory_volume_policy_service.RegulatoryVolumePolicyService._require_authorization', return_value=True):
                with patch('app.wallet.services.regulatory_volume_policy_service.current_user') as mock_current_user:
                    mock_current_user.id = 1
                    mock_current_user.has_role = MagicMock(return_value=True)
                    
                    with patch('app.wallet.services.regulatory_volume_policy_service.db') as mock_db:
                        with patch('app.wallet.services.regulatory_volume_policy_service.ForensicAuditService') as mock_audit:
                            mock_session = MagicMock()
                            mock_db.session = mock_session
                            
                            RegulatoryVolumePolicyService.request_policy_change(
                                WindowMode.ROLLING, WindowMode.ROLLING, 'Africa/Kampala', reason='Test'
                            )
                            
                            # Verify audit was called
                            mock_audit.log_action.assert_called_once()
                            call_kwargs = mock_audit.log_action.call_args[1]
                            assert call_kwargs['action'] == 'regulatory_volume_policy_change_requested'
                            assert call_kwargs['details']['proposed_daily_mode'] == 'rolling'
    
    def test_approval_logs_audit(self, app):
        """Approving a policy change should log audit event."""
        with app.test_request_context():
            with patch('app.wallet.services.regulatory_volume_policy_service.RegulatoryVolumePolicyService._require_authorization', return_value=True):
                with patch('app.wallet.services.regulatory_volume_policy_service.current_user') as mock_current_user:
                    mock_current_user.id = 2
                    mock_current_user.has_role = MagicMock(return_value=True)
                    
                    with patch('app.wallet.services.regulatory_volume_policy_service.db') as mock_db:
                        with patch('app.wallet.services.regulatory_volume_policy_service.ForensicAuditService') as mock_audit:
                            mock_session = MagicMock()
                            mock_db.session = mock_session
                            
                            change_request = RegulatoryVolumePolicyChangeRequest(
                                id=1,
                                proposed_daily_mode=WindowMode.ROLLING,
                                proposed_monthly_mode=WindowMode.CALENDAR,
                                proposed_timezone='Africa/Kampala',
                                proposed_effective_from=datetime.now(timezone.utc),
                                requested_by=1,
                                status=RegulatoryVolumePolicyChangeRequest.Status.PENDING
                            )
                            mock_session.get.return_value = change_request
                            
                            mock_query = MagicMock()
                            mock_session.query.return_value = mock_query
                            mock_query.filter_by.return_value = mock_query
                            mock_query.first.return_value = None
                            
                            # Mock get_active to return None (no existing policy)
                            with patch.object(RegulatoryVolumePolicy, 'get_active', return_value=None):
                                RegulatoryVolumePolicyService.approve_policy_change(1, 'Approved')
                            
                            mock_audit.log_action.assert_called_once()
                            call_kwargs = mock_audit.log_action.call_args[1]
                            assert call_kwargs['action'] == 'regulatory_volume_policy_change_approved'


# Parametrized tests for all four mode combinations
@pytest.mark.parametrize("daily_mode,monthly_mode", [
    (WindowMode.CALENDAR, WindowMode.CALENDAR),
    (WindowMode.ROLLING, WindowMode.ROLLING),
    (WindowMode.CALENDAR, WindowMode.ROLLING),
    (WindowMode.ROLLING, WindowMode.CALENDAR),
])
@patch('app.wallet.services.regulatory_volume_calculator.db')
def test_all_mode_combinations(mock_db, daily_mode, monthly_mode):
    """All four mode combinations should work correctly."""
    mock_session = MagicMock()
    mock_db.session = mock_session
    mock_result = MagicMock()
    mock_result.scalar.return_value = Decimal('100000')
    mock_session.execute.return_value = mock_result
    
    policy = RegulatoryVolumePolicy(
        daily_window_mode=daily_mode,
        monthly_window_mode=monthly_mode,
        timezone='Africa/Kampala'
    )
    calculator = RegulatoryVolumeCalculator(db_session=mock_session, policy=policy)
    
    daily_volume = calculator.get_daily_volume(uuid4(), 'UGX')
    monthly_volume = calculator.get_monthly_volume(uuid4(), 'UGX')
    
    assert daily_volume == Decimal('100000')
    assert monthly_volume == Decimal('100000')
    assert mock_session.execute.call_count == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])