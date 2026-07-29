# app/accommodation/services/verification_engine.py
"""
Automated Verification Engine - Manages automated trust score thresholds and auto-approval logic for properties.
"""

from app.accommodation.models.property import Property
from app.accommodation.services.trust_service import PropertyTrustService
from app.accommodation.services.readiness_service import AccommodationReadinessService

class AutomatedVerificationEngine:
    """Evaluates properties against automated verification and trust thresholds."""

    @staticmethod
    def evaluate_property(property: Property) -> dict:
        """
        Evaluates trust score and readiness, updating property scores and determining if auto-approval is eligible.
        """
        trust_score, trust_breakdown = PropertyTrustService.compute_trust_score(property)
        can_book, readiness_failures = AccommodationReadinessService.check_readiness(property)

        property.trust_score = trust_score
        readiness_score = 100.0 if can_book else max(0.0, 100.0 - (len(readiness_failures) * 15.0))
        property.readiness_score = readiness_score

        auto_approved = False
        if trust_score >= 80.0 and can_book and property.status in ["draft", "submitted", "pending_review"]:
            property.status = "active"
            property.is_verified = True
            property.verification_status = "verified"
            auto_approved = True

        return {
            "trust_score": trust_score,
            "trust_breakdown": trust_breakdown,
            "can_book": can_book,
            "readiness_score": readiness_score,
            "readiness_failures": readiness_failures,
            "auto_approved": auto_approved
        }
