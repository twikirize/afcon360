# app/kyc/__init__.py

"""
KYC module initialization.

Provides access to models, services, and verification utilities
for the Bank of Uganda compliant KYC workflow.
"""

from app.kyc.models import KycRecord
# Import routes lazily to avoid circular imports
# from app.kyc.routes import kyc_bp
from app.kyc import nira_verification as nira

__all__ = [
    "KycRecord",
    # "KycService",  # Removed to prevent circular import
    # "kyc_bp",      # Removed to prevent circular import
    "nira"
]

# Lazy imports for services
def get_kyc_service():
    from app.kyc.services import KycService
    return KycService

# Lazy import for blueprint
def get_kyc_bp():
    from app.kyc.routes import kyc_bp
    return kyc_bp
