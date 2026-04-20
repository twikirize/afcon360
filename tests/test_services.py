"""
Test that services load correctly.
"""
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'app')))

def test_kyc_service():
    """Test KYC service loads."""
    try:
        from app.kyc.services import KycService
        print("[OK] KYC service loaded successfully")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to load KYC service: {e}")
        return False

def test_auth_service():
    """Test auth service loads."""
    try:
        from app.auth.services import register_user
        print("[OK] Auth service loaded successfully")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to load auth service: {e}")
        return False

def test_forensic_audit():
    """Test forensic audit service loads."""
    try:
        from app.audit.forensic_audit import ForensicAuditService
        print("[OK] Forensic audit service loaded successfully")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to load forensic audit service: {e}")
        return False

if __name__ == "__main__":
    results = []
    results.append(test_kyc_service())
    results.append(test_auth_service())
    results.append(test_forensic_audit())

    if all(results):
        print("\n[SUCCESS] All services loaded successfully!")
        sys.exit(0)
    else:
        print("\n[FAILURE] Some services failed to load")
        sys.exit(1)
