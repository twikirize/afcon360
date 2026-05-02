"""
Simple test to load services.
"""
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'app')))

try:
    from app.kyc.services import KycService
    print("KYC service loaded successfully")
except Exception as e:
    print(f"Failed to load KYC service: {e}")
    sys.exit(1)

try:
    from app.auth.services import register_user
    print("Auth service loaded successfully")
except Exception as e:
    print(f"Failed to load auth service: {e}")
    sys.exit(1)

try:
    from app.audit.forensic_audit import ForensicAuditService
    print("Forensic audit service loaded successfully")
except Exception as e:
    print(f"Failed to load forensic audit service: {e}")
    sys.exit(1)

print("All services loaded successfully!")
sys.exit(0)
