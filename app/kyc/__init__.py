# app/kyc/__init__.py

"""
KYC module initialization.

Provides access to models and services for the KYC workflow.
"""

from app.kyc.models import KycRecord
from app.kyc.services import KycService

__all__ = [
    "KycRecord",
    "KycService"
]

