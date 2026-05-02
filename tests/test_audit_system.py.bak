"""
Test the comprehensive audit system - Simplified version
Only tests existence of audit infrastructure without database dependencies
"""
import pytest
from app.audit.comprehensive_audit import (
    FinancialAuditLog, APIAuditLog, SecurityEventLog,
    DataAccessLog, DataChangeLog, AuditService,
    TransactionType, APICallStatus, AuditSeverity, DataAccessType
)
from app.identity.models.user import User
from app.wallet.services.audit import WalletAudit


class TestAuditSystem:
    """Test comprehensive audit system - infrastructure existence only"""

    def test_audit_classes_exist(self):
        """Verify all audit model classes exist"""
        assert FinancialAuditLog is not None
        assert APIAuditLog is not None
        assert SecurityEventLog is not None
        assert DataAccessLog is not None
        assert DataChangeLog is not None
        assert AuditService is not None

    def test_enum_classes_exist(self):
        """Verify all enum classes exist"""
        assert TransactionType is not None
        assert APICallStatus is not None
        assert AuditSeverity is not None
        assert DataAccessType is not None

        # Verify enum values exist
        assert TransactionType.DEPOSIT == "deposit"
        assert TransactionType.WITHDRAWAL == "withdrawal"
        assert TransactionType.TRANSFER == "transfer"

        assert APICallStatus.SUCCESS == "success"
        assert APICallStatus.FAILURE == "failure"

        assert AuditSeverity.INFO == "info"
        assert AuditSeverity.WARNING == "warning"
        assert AuditSeverity.CRITICAL == "critical"

        assert DataAccessType.READ == "read"
        assert DataAccessType.EXPORT == "export"

    def test_audit_service_methods_exist(self):
        """Verify AuditService methods exist"""
        assert hasattr(AuditService, 'financial')
        assert hasattr(AuditService, 'api_call')
        assert hasattr(AuditService, 'data_access')
        assert hasattr(AuditService, 'security')
        assert hasattr(AuditService, 'data_change')
        assert hasattr(AuditService, 'compliance')

    def test_wallet_audit_methods_exist(self):
        """Test WalletAudit logging methods exist"""
        # Test that WalletAudit methods exist
        assert hasattr(WalletAudit, 'log_deposit_initiated')
        assert hasattr(WalletAudit, 'log_deposit_completed')
        assert hasattr(WalletAudit, 'log_withdrawal_initiated')
        assert hasattr(WalletAudit, 'log_transfer_initiated')
        assert hasattr(WalletAudit, 'log_security_alert')

        # Test that new dispute methods exist
        assert hasattr(WalletAudit, 'log_dispute_created')
        assert hasattr(WalletAudit, 'log_dispute_resolved')

        # Test other important methods
        assert hasattr(WalletAudit, 'log_wallet_created')
        assert hasattr(WalletAudit, 'log_wallet_frozen')
        assert hasattr(WalletAudit, 'log_wallet_unfrozen')
        assert hasattr(WalletAudit, 'log_balance_change')
        assert hasattr(WalletAudit, 'log_commission_earned')
        assert hasattr(WalletAudit, 'log_payout_request_created')

    def test_user_audit_helpers_exist(self):
        """Test User model audit helper methods exist"""
        # Test that audit helper methods exist
        assert hasattr(User, 'audit_org_member_added')
        assert hasattr(User, 'audit_org_member_removed')
        assert hasattr(User, 'audit_org_role_assigned')
        assert hasattr(User, 'audit_org_role_revoked')
        assert hasattr(User, 'audit_admin_impersonation_start')
        assert hasattr(User, 'audit_admin_impersonation_end')

        # Test MFA audit methods exist on User class
        assert hasattr(User, 'enable_mfa')
        assert hasattr(User, 'disable_mfa')

        # Test APIKey audit methods
        from app.identity.models.user import APIKey
        assert hasattr(APIKey, 'create_with_audit')
        assert hasattr(APIKey, 'revoke_with_audit')

    def test_audit_model_static_methods_exist(self):
        """Verify audit model static methods exist"""
        assert hasattr(FinancialAuditLog, 'log_transaction')
        assert hasattr(APIAuditLog, 'log_api_call')
        assert hasattr(SecurityEventLog, 'log_event')
        assert hasattr(DataAccessLog, 'log_access')
        assert hasattr(DataChangeLog, 'log_change')

    def test_audit_infrastructure_complete(self):
        """Verify all required audit infrastructure is present"""
        # Core audit models
        required_classes = [
            'FinancialAuditLog',
            'APIAuditLog',
            'SecurityEventLog',
            'DataAccessLog',
            'DataChangeLog',
            'AuditService'
        ]

        for class_name in required_classes:
            assert class_name in globals() or hasattr(__import__(__name__), class_name)

        # Core enums
        required_enums = [
            'TransactionType',
            'APICallStatus',
            'AuditSeverity',
            'DataAccessType'
        ]

        for enum_name in required_enums:
            assert enum_name in globals() or hasattr(__import__(__name__), enum_name)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
