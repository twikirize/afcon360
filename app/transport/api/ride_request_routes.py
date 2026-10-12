"""BOOKING-LIFECYCLE-REQUEST-CREATE (Stage 3B, Phase 2A).

Rider request-creation endpoint. Authenticated + commitment-gated
(login, profile completion, KYC tier 2 — the same gates as the legacy
rider booking route). Creates zero Bookings by construction.
"""
import logging

from flask import request
from flask_login import current_user, login_required
from flask_restful import Resource

from app.auth.decorators import require_profile_completion
from app.auth.kyc_compliance import require_kyc_tier
from app.transport.services.ride_request_service import (
    IdempotencyConflictError,
    RideRequestService,
    serialize_request,
)
from app.utils.exceptions import ValidationError

logger = logging.getLogger(__name__)


class RideRequestCreateResource(Resource):
    """POST /api/transport/ride-requests — create a pre-Booking ride request."""

    # Outermost runs first: anonymous callers get the KYC gate's 401
    # (same as login_required's JSON 401 for /api/ paths).
    method_decorators = [
        login_required,
        require_profile_completion,
        require_kyc_tier(2),
    ]

    def post(self):
        data = request.get_json(silent=True) or {}
        try:
            result = RideRequestService.create_request(current_user.id, data)
        except IdempotencyConflictError as e:
            logger.warning("Ride-request idempotency conflict for user %s: %s",
                           getattr(current_user, "id", None), e.message)
            return {"success": False, "error": e.message,
                    "code": "idempotency_conflict"}, 409
        except ValidationError as e:
            return {"success": False, "error": e.message}, 400

        ride_request = result["request"]
        cycle = result["cycle"]
        replayed = bool(result.get("replayed"))
        logger.info("Ride-request %s for user %s (replayed=%s)",
                    ride_request.public_id,
                    getattr(current_user, "id", None), replayed)
        return {
            "success": True,
            "data": serialize_request(ride_request, cycle),
            "replayed": replayed,
        }, (200 if replayed else 201)
