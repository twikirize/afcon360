"""
Audit system tests - Updated for new wallet structure
"""
import pytest

def test_audit_imports():
    """Test that audit modules import correctly"""
    # Check for new admin audit service
    from app.wallet.services.admin_audit_service import AdminAuditService
    assert AdminAuditService is not None

def test_audit_log_exists():
    """Test audit log model exists"""
    from app.wallet.models.admin_audit import AdminAuditLog
    assert AdminAuditLog is not None

def test_audit_model_attributes():
    """Test audit model has required attributes"""
    from app.wallet.models.admin_audit import AdminAuditLog
    # Check expected fields
    assert hasattr(AdminAuditLog, 'action')
    assert hasattr(AdminAuditLog, 'user_id')
    assert hasattr(AdminAuditLog, 'timestamp')
