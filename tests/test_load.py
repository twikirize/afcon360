"""
Proper pytest tests for service loading.
"""
import pytest
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'app')))

def test_kyc_service_load():
    """Test that KYC service can be loaded"""
    try:
        from app.kyc.services import KycService
        assert KycService is not None
    except ImportError as e:
        pytest.fail(f"Failed to load KYC service: {e}")

def test_auth_service_load():
    """Test that auth service can be loaded"""
    try:
        from app.auth.services import register_user
        assert callable(register_user)
    except ImportError as e:
        pytest.fail(f"Failed to load auth service: {e}")

def test_forensic_audit_service_load():
    """Test that forensic audit service can be loaded"""
    try:
        from app.audit.forensic_audit import ForensicAuditService
        assert ForensicAuditService is not None
    except ImportError as e:
        pytest.fail(f"Failed to load forensic audit service: {e}")

def test_all_services_load():
    """Test all services load together"""
    from app.kyc.services import KycService
    from app.auth.services import register_user
    from app.audit.forensic_audit import ForensicAuditService
    
    assert KycService is not None
    assert callable(register_user)
    assert ForensicAuditService is not None
