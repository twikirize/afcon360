# app/accommodation/services/trust_service.py
"""
Property Trust Service - Computes 0-100 property trust scores based on owner KYC/KYB and property verification signals.
"""

from typing import Dict, Any, Tuple
from app.accommodation.models.property import Property
from app.identity.models.user import User

class PropertyTrustService:
    """Computes trust score for accommodation properties."""

    @staticmethod
    def compute_trust_score(property: Property) -> Tuple[float, Dict[str, Any]]:
        """
        Computes a 0-100 trust score for a property.
        Returns (score, breakdown_dict).
        """
        score = 0.0
        breakdown = {
            "identity_signals": 0.0,
            "property_signals": 0.0,
            "risk_penalties": 0.0,
            "details": []
        }

        owner = None
        if property.owner_user_id:
            owner = User.query.get(property.owner_user_id)

        # 1. Identity Signals (Max 50 points)
        if owner:
            if getattr(owner, "email_verified", False):
                score += 10.0
                breakdown["identity_signals"] += 10.0
                breakdown["details"].append("Email verified (+10)")
            if getattr(owner, "phone_verified", False):
                score += 10.0
                breakdown["identity_signals"] += 10.0
                breakdown["details"].append("Phone verified (+10)")
            if getattr(owner, "id_verified", False) or getattr(owner, "kyc_verified", False):
                score += 20.0
                breakdown["identity_signals"] += 20.0
                breakdown["details"].append("Government ID / KYC verified (+20)")
            if getattr(owner, "address_verified", False):
                score += 10.0
                breakdown["identity_signals"] += 10.0
                breakdown["details"].append("Address verified (+10)")
        elif property.owner_org_id:
            score += 40.0
            breakdown["identity_signals"] += 40.0
            breakdown["details"].append("Organisation KYB owner (+40)")

        # 2. Property Signals (Max 40 points)
        if property.main_image:
            score += 10.0
            breakdown["property_signals"] += 10.0
            breakdown["details"].append("Main photo present (+10)")

        if property.gallery and len(property.gallery) >= 3:
            score += 10.0
            breakdown["property_signals"] += 10.0
            breakdown["details"].append("Rich photo gallery >= 3 (+10)")

        if property.latitude and property.longitude:
            score += 10.0
            breakdown["property_signals"] += 10.0
            breakdown["details"].append("Geocoded location (+10)")

        if property.description and len(property.description) >= 50:
            score += 10.0
            breakdown["property_signals"] += 10.0
            breakdown["details"].append("Detailed description (+10)")

        # 3. Verification Bonus (Max 10 points)
        if property.is_verified or property.verification_status == "verified":
            score += 10.0
            breakdown["property_signals"] += 10.0
            breakdown["details"].append("Admin verified (+10)")

        # 4. Risk Penalties
        if getattr(property, "policy_violations", 0) > 0:
            penalty = property.policy_violations * 10.0
            score -= penalty
            breakdown["risk_penalties"] -= penalty
            breakdown["details"].append(f"Policy violations penalty (-{penalty})")

        # Clamp score between 0 and 100
        final_score = max(0.0, min(100.0, score))
        return round(final_score, 2), breakdown
