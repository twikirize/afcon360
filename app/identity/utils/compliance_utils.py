# app/identity/utils/compliance_utils.py

from datetime import datetime
from app.identity.models.compliance_settings import ComplianceSettings

def can_perform_operation(entity, requirement_key):
    """
    Check if an entity (Organisation or Individual) can perform a given operation
    based on compliance settings and verification state.
    """
    setting = ComplianceSettings.query.filter_by(requirement=requirement_key).first()
    if not setting or not setting.is_enabled:
        return True  # requirement disabled

    if setting.enforcement_level == "mandatory":
        return entity.is_fully_verified()
    elif setting.enforcement_level == "conditional":
        return entity.has_partial_verification()
    else:
        return True  # optional


def compliance_risk_tier(entity):
    """
    Return a categorical risk tier: low, medium, high.
    """
    if entity.is_fully_verified() and not entity.has_expired_license and not entity.has_expired_document:
        return "low"
    elif entity.has_partial_verification() or entity.has_expired_document:
        return "medium"
    else:
        return "high"


def compliance_level(entity):
    """
    Return a progressive compliance level (0–3).
    Level 0: Registered only
    Level 1: Partial verification
    Level 2: Fully verified
    Level 3: Fully verified + controllers + licenses
    """
    if entity.is_fully_verified() and getattr(entity, "controllers", None) and getattr(entity, "licenses", None):
        return 3
    elif entity.is_fully_verified():
        return 2
    elif entity.has_partial_verification():
        return 1
    else:
        return 0


def compliance_capabilities(entity):
    """
    Return a dictionary of capability flags for operations.
    These flags can be used to gate features dynamically.
    """
    return {
        "can_list_offers": True,  # always allowed
        "can_receive_payments": entity.has_partial_verification(),
        "can_withdraw_funds": entity.is_fully_verified(),
    }


def compliance_status_light(entity):
    """
    Return a traffic light style compliance status (green/amber/red).
    """
    if entity.is_fully_verified():
        return "green"
    elif entity.has_partial_verification():
        return "amber"
    else:
        return "red"
