"""
Simple import test without database
"""
def test_import_kyc():
    """Test that KYC service can be imported"""
    from app.kyc.services import KycService
    assert KycService is not None

def test_import_auth():
    """Test that auth service can be imported"""
    from app.auth.services import register_user
    assert callable(register_user)

def test_import_audit():
    """Test that audit service can be imported"""
    from app.audit.forensic_audit import ForensicAuditService
    assert ForensicAuditService is not None
