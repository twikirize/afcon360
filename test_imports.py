"""
Test that imports work correctly.
"""
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'app')))

def test_import_forensic_audit():
    """Test importing ForensicAuditService."""
    try:
        from app.audit.forensic_audit import ForensicAuditService
        print("[OK] Successfully imported ForensicAuditService")
        assert True
    except ImportError as e:
        print(f"[ERROR] Failed to import ForensicAuditService: {e}")
        assert False

def test_import_kyc_service():
    """Test importing KycService."""
    try:
        from app.kyc.services import KycService
        print("[OK] Successfully imported KycService")
        assert True
    except ImportError as e:
        print(f"[ERROR] Failed to import KycService: {e}")
        assert False

def test_import_auth_service():
    """Test importing auth services."""
    try:
        from app.auth.services import register_user
        print("[OK] Successfully imported register_user")
        assert True
    except ImportError as e:
        print(f"[ERROR] Failed to import auth services: {e}")
        assert False

if __name__ == "__main__":
    test_import_forensic_audit()
    test_import_kyc_service()
    test_import_auth_service()
    print("[SUCCESS] All import tests passed!")
