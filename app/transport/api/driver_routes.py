# app/transport/api/driver_routes.py
from __future__ import annotations
from flask import request, jsonify
from flask_restful import Resource
from flask_login import current_user, login_required
from app.extensions import db
from app.transport.models import DriverProfile, DriverVehicleHistory, Booking, BookingPayment, Vehicle
from app.utils.enums import BookingStatus, PaymentStatus, ComplianceStatus, VerificationTier
from app.auth.decorators import admin_required
from app.transport.decorator import transport_admin_required
from app.transport.utils.helpers import paginate, filter_query, sort_query
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import or_, func
import sqlalchemy as sa
import logging
import math
import re
from typing import TYPE_CHECKING, Any, Optional, cast

if TYPE_CHECKING:
    from app.identity.models.user import User
    from sqlalchemy.engine import Result

logger = logging.getLogger(__name__)

# Fields allowed for sorting - prevents arbitrary column injection
DRIVER_SORT_FIELDS = [
    "created_at", "updated_at", "average_rating",
    "reliability_score", "safety_score", "total_trips",
    "compliance_status", "verification_tier"
]


def parse_bool(value: Optional[str]) -> Optional[bool]:
    """Parse boolean query parameter safely.
    
    Args:
        value: String value from query parameter
        
    Returns:
        bool or None
        
    Raises:
        ValueError: If value is not a valid boolean string
    """
    if value is None:
        return None
    value = value.strip().lower()
    if value in ("true", "1", "yes"):
        return True
    if value in ("false", "0", "no"):
        return False
    raise ValueError("Invalid boolean value")


def parse_positive_int(value: Optional[str], max_value: Optional[int] = None) -> Optional[int]:
    """Parse positive integer query parameter safely.
    
    Args:
        value: String value from query parameter
        max_value: Optional maximum allowed value
        
    Returns:
        int or None
        
    Raises:
        ValueError: If value is not a valid positive integer
    """
    if value is None:
        return None
    try:
        result = int(value)
        if result < 0:
            raise ValueError("Must be non-negative")
        if max_value is not None and result > max_value:
            raise ValueError(f"Must not exceed {max_value}")
        return result
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid integer value: {e}")


class DriverListResource(Resource):
    """GET/POST /api/transport/drivers"""

    @admin_required
    def get(self):
        """List drivers with filtering, sorting, and pagination"""

        # ------------------------------------------------------------------
        # Build base query
        # ------------------------------------------------------------------
        query = DriverProfile.query.filter_by(is_deleted=False)

        # ------------------------------------------------------------------
        # Filter via helpers - safe boolean parsing
        # ------------------------------------------------------------------
        try:
            is_online = parse_bool(request.args.get("is_online"))
            is_available = parse_bool(request.args.get("is_available"))
        except ValueError as e:
            return {"success": False, "error": str(e)}, 400

        filters = {
            "verification_tier":  request.args.get("verification_tier"),
            "compliance_status":  request.args.get("compliance_status"),
            "is_online":          is_online,
            "is_available":       is_available,
            "average_rating__gte": request.args.get("min_rating", type=float),
        }
        query = filter_query(query, DriverProfile, filters)

        # ------------------------------------------------------------------
        # Search (join required - handled separately from filter_query)
        # ------------------------------------------------------------------
        search = request.args.get("search")
        if search:
            from app.identity.models.user import User
            query = query.join(DriverProfile.user).filter(
                or_(
                    DriverProfile.driver_code.ilike(f"%{search}%"),
                    User.username.ilike(f"%{search}%"),
                    User.email.ilike(f"%{search}%"),
                )
            )

        # ------------------------------------------------------------------
        # Sort via helpers
        # ------------------------------------------------------------------
        query = sort_query(query, DriverProfile, DRIVER_SORT_FIELDS)

        # ------------------------------------------------------------------
        # Paginate via helpers
        # ------------------------------------------------------------------
        result = paginate(query)

        return {
            "success": True,
            "data": {
                "items": [
                    d.to_dict(exclude=["license_number_encrypted"])
                    for d in result["items"]
                ],
                "total":    result["total"],
                "page":     result["page"],
                "per_page": result["per_page"],
                "pages":    result["pages"],
                "has_next": result["has_next"],
                "has_prev": result["has_prev"],
            },
        }

    @admin_required
    def post(self):
        """Create new driver"""
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        # Input validation
        user_id = data.get("user_id")
        if not user_id:
            return {"success": False, "error": "user_id is required"}, 400

        from app.identity.models.user import User
        user = User.query.get(user_id)
        if not user:
            return {"success": False, "error": "User not found"}, 404

        # Check if user already has a driver profile
        existing = DriverProfile.query.filter_by(user_id=user_id, is_deleted=False).first()
        if existing:
            return {"success": False, "error": "User already has a driver profile"}, 409

        driver_code = data.get("driver_code")
        if not driver_code:
            return {"success": False, "error": "driver_code is required"}, 400
        # Check driver_code uniqueness
        if DriverProfile.query.filter_by(driver_code=driver_code, is_deleted=False).first():
            return {"success": False, "error": "driver_code already exists"}, 409

        license_number = data.get("license_number")

        # Validate commission rate
        commission_rate = data.get("commission_rate", 15.00)
        try:
            commission_rate = float(commission_rate)
            if not (0 <= commission_rate <= 100):
                return {"success": False, "error": "commission_rate must be between 0 and 100"}, 400
        except (ValueError, TypeError):
            return {"success": False, "error": "commission_rate must be a valid number"}, 400

        # Validate passenger capacity
        max_passenger_capacity = data.get("max_passenger_capacity", 4)
        try:
            max_passenger_capacity = int(max_passenger_capacity)
            if not (1 <= max_passenger_capacity <= 50):
                return {"success": False, "error": "max_passenger_capacity must be between 1 and 50"}, 400
        except (ValueError, TypeError):
            return {"success": False, "error": "max_passenger_capacity must be a valid integer"}, 400

        # Validate luggage capacity
        max_luggage_capacity = data.get("max_luggage_capacity", 2)
        try:
            max_luggage_capacity = int(max_luggage_capacity)
            if not (0 <= max_luggage_capacity <= 20):
                return {"success": False, "error": "max_luggage_capacity must be between 0 and 20"}, 400
        except (ValueError, TypeError):
            return {"success": False, "error": "max_luggage_capacity must be a valid integer"}, 400

        # Validate vehicle classes
        vehicle_classes = data.get("vehicle_classes", ["comfort"])
        valid_vehicle_classes = {"economy", "comfort", "premium", "luxury", "van", "bus"}
        if not isinstance(vehicle_classes, list) or not vehicle_classes:
            return {"success": False, "error": "vehicle_classes must be a non-empty list"}, 400
        for vc in vehicle_classes:
            if vc.lower() not in valid_vehicle_classes:
                return {"success": False, "error": f"Invalid vehicle class: {vc}. Valid: {sorted(valid_vehicle_classes)}"}, 400

        # Validate service types
        service_types = data.get("service_types", ["on_demand"])
        valid_service_types = {"on_demand", "scheduled", "airport", "corporate"}
        if not isinstance(service_types, list) or not service_types:
            return {"success": False, "error": "service_types must be a non-empty list"}, 400
        for st in service_types:
            if st.lower() not in valid_service_types:
                return {"success": False, "error": f"Invalid service type: {st}. Valid: {sorted(valid_service_types)}"}, 400

        try:
            driver = DriverProfile(
                user_id=user_id,
                driver_code=driver_code,
                license_number=license_number,
                languages_spoken=data.get("languages_spoken", ["en"]),
                vehicle_classes=[vc.lower() for vc in vehicle_classes],
                service_types=[st.lower() for st in service_types],
                max_passenger_capacity=max_passenger_capacity,
                max_luggage_capacity=max_luggage_capacity,
                commission_rate=commission_rate,
            )
            db.session.add(driver)
            db.session.commit()
            logger.info(f"Driver created: driver_id={driver.id}")
            return {
                "success": True,
                "data": driver.to_dict(exclude=["license_number_encrypted"]),
            }, 201

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating driver: {e}", exc_info=True)
            return {"success": False, "error": "Failed to create driver"}, 500


class DriverDetailResource(Resource):
    """GET/PUT/DELETE /api/transport/drivers/<int:driver_id>"""

    @admin_required
    def get(self, driver_id):
        """Get single driver with full detail"""
        # Exclude soft-deleted drivers
        driver = DriverProfile.query.filter_by(
            id=driver_id, is_deleted=False
        ).first_or_404()

        recent_trips = (
            Booking.query
            .filter_by(assigned_driver_id=driver_id, is_deleted=False)
            .order_by(Booking.created_at.desc())
            .limit(10)
            .all()
        )

        total_earnings = (
            db.session.query(func.sum(Booking.final_price))
            .filter(  # type: ignore[arg-type]
                Booking.assigned_driver_id == driver_id,
                Booking.payment_status == PaymentStatus.CAPTURED,
                Booking.is_deleted == False,
            )
            .scalar() or 0
        )

        return {
            "success": True,
            "data": {
                "driver": driver.to_dict(exclude=["license_number_encrypted"]),
                "current_assignment": (
                    driver.current_assignment.to_dict()
                    if driver.current_assignment else None
                ),
                "recent_trips": [t.to_dict() for t in recent_trips],
                "total_earnings": float(total_earnings),
                "vehicles": [v.to_dict() for v in driver.owned_vehicles],
            },
        }

    @transport_admin_required
    def put(self, driver_id):
        """Update driver fields"""
        driver = DriverProfile.query.get_or_404(driver_id)
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        updatable_fields = [
            "languages_spoken", "vehicle_classes", "service_types",
            "operational_zones", "preferred_zones",
            "max_passenger_capacity", "max_luggage_capacity",
            "commission_rate", "is_online", "is_available",
        ]
        # SUPPLY-00c: enforce is_online => is_available against the projected
        # end state before applying any field.
        projected_online = data.get("is_online", driver.is_online)
        projected_available = data.get("is_available", driver.is_available)
        if projected_online and not projected_available:
            return {
                "success": False,
                "error": "Driver cannot be online without being available",
            }, 422
        for field in updatable_fields:
            if field in data:
                setattr(driver, field, data[field])

        try:
            db.session.commit()
            logger.info(f"Driver {driver_id} updated")
            return {
                "success": True,
                "data": driver.to_dict(exclude=["license_number_encrypted"]),
            }
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating driver {driver_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500

    @admin_required
    def delete(self, driver_id):
        """Soft delete driver"""
        # Exclude soft-deleted drivers
        driver = DriverProfile.query.filter_by(
            id=driver_id, is_deleted=False
        ).first_or_404()
        driver.is_deleted = True
        driver.deleted_at = datetime.now(timezone.utc)
        driver.is_online = False
        driver.is_available = False

        try:
            db.session.commit()
            logger.info(f"Driver {driver_id} soft-deleted")
            return {"success": True, "message": "Driver deleted"}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting driver {driver_id}: {e}", exc_info=True)
            return {"success": False, "error": "Failed to delete driver"}, 500


class DriverVerificationResource(Resource):
    """POST /api/transport/drivers/<int:driver_id>/verification"""

    @admin_required
    def post(self, driver_id):
        """Update driver verification status"""
        # Exclude soft-deleted drivers
        driver = DriverProfile.query.filter_by(
            id=driver_id, is_deleted=False
        ).first_or_404()
        
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        action = data.get("action")

        if action == "verify_license":
            driver.license_verified = True
            driver.license_verified_at = datetime.now(timezone.utc)
            # Use server-side actor identity, not client-supplied
            driver.license_verified_by = current_user.id

        elif action == "verify_police":
            driver.police_clearance_verified = True
            driver.police_clearance_date = datetime.now(timezone.utc)
            driver.background_check_reference = data.get("reference")

        elif action == "verify_tier":
            # Use the canonical persisted enum values; invented display tiers
            # do not exist in the PostgreSQL verificationtier enum.
            tier = data.get("tier")
            try:
                verification_tier = VerificationTier(tier)
            except (TypeError, ValueError):
                return {
                    "success": False,
                    "error": f"Invalid tier. Valid: {VerificationTier.values()}",
                }, 400
            driver.verification_tier = verification_tier

        elif action == "update_compliance":
            # Validate compliance status against enum
            status = data.get("status")
            try:
                compliance_status = ComplianceStatus(status)
            except (TypeError, ValueError):
                valid_statuses = [s.value for s in ComplianceStatus]
                return {"success": False, "error": f"Invalid compliance status. Valid: {valid_statuses}"}, 400
            driver.compliance_status = compliance_status

        else:
            return {"success": False, "error": f"Unknown action: {action}"}, 400

        try:
            db.session.commit()
            logger.info(f"Driver {driver_id} verification updated: action={action}, by={current_user.id}")
            return {
                "success": True,
                "data": driver.to_dict(exclude=["license_number_encrypted"]),
            }
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating verification for driver {driver_id}: {e}", exc_info=True)
            return {"success": False, "error": "Failed to update verification"}, 500


class DriverLocationResource(Resource):
    """GET/POST /api/transport/drivers/<int:driver_id>/location"""

    @admin_required
    def get(self, driver_id):
        """Get driver's last known location"""
        # FIX 1: Exclude soft-deleted drivers
        driver = DriverProfile.query.filter_by(
            id=driver_id, is_deleted=False
        ).first_or_404()
        
        return {
            "success": True,
            "data": {
                "last_location": driver.last_location,
                "location_updated_at": (
                    driver.location_updated_at.isoformat()
                    if driver.location_updated_at else None
                ),
                "is_online": driver.is_online,
                "last_seen_at": (
                    driver.last_seen_at.isoformat()
                    if driver.last_seen_at else None
                ),
            },
        }

    @login_required
    def post(self, driver_id):
        """Update driver location (mobile app) — canonical TrackingService path."""
        from app.auth.helpers import has_global_role

        # FIX 1: Exclude soft-deleted drivers
        driver = DriverProfile.query.filter_by(
            id=driver_id, is_deleted=False
        ).first_or_404()
        
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        is_admin = has_global_role(current_user, "admin", "super_admin", "owner")
        if driver.user_id != current_user.id and not is_admin:
            logger.warning(
                f"Location publish denied: user={current_user.id} tried to update "
                f"driver {driver_id} owned by user {driver.user_id}"
            )
            return {"success": False, "error": "not allowed to update this driver's location"}, 403

        # Explicit numeric/range validation at API boundary
        try:
            if isinstance(data.get("latitude"), bool) or isinstance(data.get("longitude"), bool):
                raise ValueError("boolean coordinates are invalid")
            latitude = float(data.get("latitude"))
            longitude = float(data.get("longitude"))
        except (TypeError, ValueError):
            return {"success": False, "error": "latitude and longitude must be valid numbers"}, 400

        if not (-90 <= latitude <= 90):
            return {"success": False, "error": "latitude must be between -90 and 90"}, 400
        if not (-180 <= longitude <= 180):
            return {"success": False, "error": "longitude must be between -180 and 180"}, 400

        # Optional fields with validation
        accuracy = data.get("accuracy")
        if accuracy is not None:
            try:
                if isinstance(accuracy, bool):
                    raise ValueError("boolean telemetry is invalid")
                accuracy = float(accuracy)
                if not math.isfinite(accuracy) or accuracy < 0:
                    return {"success": False, "error": "accuracy must be non-negative"}, 400
            except (TypeError, ValueError):
                return {"success": False, "error": "accuracy must be a valid number"}, 400

        speed = data.get("speed")
        if speed is not None:
            try:
                if isinstance(speed, bool):
                    raise ValueError("boolean telemetry is invalid")
                speed = float(speed)
                if not math.isfinite(speed) or speed < 0:
                    return {"success": False, "error": "speed must be non-negative"}, 400
            except (TypeError, ValueError):
                return {"success": False, "error": "speed must be a valid number"}, 400

        heading = data.get("heading")
        if heading is not None:
            try:
                if isinstance(heading, bool):
                    raise ValueError("boolean telemetry is invalid")
                heading = float(heading)
                if not math.isfinite(heading) or not (0 <= heading <= 360):
                    return {"success": False, "error": "heading must be between 0 and 360"}, 400
            except (TypeError, ValueError):
                return {"success": False, "error": "heading must be a valid number"}, 400

        client_ts = data.get("client_ts")
        if client_ts is not None:
            try:
                if isinstance(client_ts, bool):
                    raise ValueError("boolean telemetry is invalid")
                client_ts = float(client_ts)
                if not math.isfinite(client_ts) or client_ts < 0:
                    return {"success": False, "error": "client_ts must be non-negative"}, 400
            except (TypeError, ValueError):
                return {"success": False, "error": "client_ts must be a valid number"}, 400

        try:
            from app.transport.services.tracking_service import get_tracking_service
            from app.utils.exceptions import ValidationError
            tracking_service = get_tracking_service()
            
            # FIX 2 & 3: Pass client_ts and do not fake accuracy as 0.0
            result = tracking_service.update_location('driver', driver.id, {
                'latitude': latitude,
                'longitude': longitude,
                'accuracy': accuracy,  # Let TrackingService handle None
                'speed': speed,
                'heading': heading,
                'client_ts': client_ts,  # Pass the GPS observation time!
            })

            # FIX 4: Check success BEFORE committing last_seen_at
            if not result.get('success'):
                db.session.rollback()
                return {"success": False, "error": result.get('message', 'Location update failed')}, 500

            driver.last_seen_at = datetime.now(timezone.utc)
            db.session.commit()

            # No body: the dashboard only needs the committed HTTP success.
            # Do not expose TrackingService's internal entity_id to clients.
            return '', 204
            
        except ValidationError as e:
            db.session.rollback()
            return {"success": False, "error": str(e)}, 400
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating location for driver {driver_id}: {e}", exc_info=True)
            return {"success": False, "error": "Failed to update location"}, 500


class DriverCsrfTokenResource(Resource):
    """GET /api/transport/csrf-token

    Reissues a fresh, session-bound CSRF token for the current authenticated
    session. Long-lived pages (e.g. the driver dashboard location pinger)
    capture the CSRF token once at load; once that token exceeds
    ``WTF_CSRF_TIME_LIMIT`` every write is rejected with a 400. This endpoint
    lets the client refresh instead of failing forever.

    It only returns a token for the caller's own session and grants no new
    authority, so it does not weaken CSRF protection.
    """

    @login_required
    def get(self):
        from flask_wtf.csrf import generate_csrf

        # Session-bound, time-limited token: never cache it anywhere.
        resp = jsonify({"success": True, "csrf_token": generate_csrf()})
        resp.headers["Cache-Control"] = "no-store"
        return resp


class DriverHistoryResource(Resource):
    """GET /api/transport/drivers/<int:driver_id>/history"""

    @admin_required
    def get(self, driver_id):
        """Get driver's vehicle assignment history"""
        # Exclude soft-deleted drivers
        driver = DriverProfile.query.filter_by(
            id=driver_id, is_deleted=False
        ).first_or_404()

        # Validate days parameter
        try:
            days = parse_positive_int(request.args.get("days", "30"), max_value=365)
        except ValueError as e:
            return {"success": False, "error": str(e)}, 400
        
        if days is None:
            days = 30
            
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        history = (
            DriverVehicleHistory.query
            .filter(
                DriverVehicleHistory.driver_id == driver_id,
                DriverVehicleHistory.started_at >= cutoff,
            )
            .order_by(DriverVehicleHistory.started_at.desc())
            .all()
        )

        return {
            "success": True,
            "data": [
                {
                    "id": h.id,
                    "vehicle": {
                        "id": h.vehicle.id,
                        "license_plate": h.vehicle.license_plate,
                        "make": h.vehicle.make,
                        "model": h.vehicle.model,
                    } if h.vehicle else None,
                    "started_at": h.started_at.isoformat(),
                    "ended_at": h.ended_at.isoformat() if h.ended_at else None,
                    "assignment_reason": h.assignment_reason,
                    "notes": h.notes,
                    "was_breakdown": h.was_breakdown,
                }
                for h in history
            ],
        }


# ===========================================================================
# TH-3-D2 - Driver offer surface + trip lifecycle (canonical dispatch)
# ===========================================================================

def _current_driver_profile():
    """The authenticated user's DriverProfile, or 403 if they are not a driver."""
    profile = DriverProfile.query.filter_by(
        user_id=current_user.id, is_deleted=False
    ).first()
    if not profile:
        return None, {
            "success": False,
            "error": "authenticated user has no driver profile",
        }, 403
    return profile, None, None


class DriverOfferListResource(Resource):
    """GET /api/transport/drivers/me/offers — live transient offers (D2)."""

    @login_required
    def get(self):
        from app.transport.services.offer_service import OfferService
        from app.transport.services.ride_request_dispatch_service import (
            RideRequestDispatchService,
        )

        profile, error, status = _current_driver_profile()
        if error:
            return error, status
        # Preserve legacy offers while adding durable request-first offers.
        # Both shapes expose the same safe driver card contract.
        try:
            offers = OfferService.list_driver_offers(profile.id) or []
        except Exception:
            logger.warning(
                "Could not load legacy driver offers; continuing with durable offers",
                exc_info=True,
            )
            offers = []
        try:
            request_offers = RideRequestDispatchService.list_driver_offers(profile.id)
        except Exception:
            logger.warning("Could not load request-first driver offers", exc_info=True)
            request_offers = []
        known = {o.get("booking_reference") for o in offers}
        offers.extend(o for o in request_offers if o.get("booking_reference") not in known)
        return {"success": True, "data": {"offers": offers}}


class DriverOfferAcceptResource(Resource):
    """POST /api/transport/drivers/me/offers/<booking_reference>/accept"""

    @login_required
    def post(self, booking_reference):
        from app.transport.services.offer_service import (
            OfferService,
            OfferUnavailableError,
        )
        from app.transport.services.assignment_service import (
            AssignmentService,
            DispatchClaimError,
        )

        profile, error, status = _current_driver_profile()
        if error:
            return error, status

        # Request-first offers select a concrete eligible vehicle at offer
        # creation time. Accept the exact server-recorded offer, not merely
        # DriverProfile.current_vehicle (which can be unset or differ from the
        # vehicle offered). The driver cannot substitute an arbitrary vehicle.
        from app.transport.models import (
            Booking, RideRequest, OfferAttempt, SearchCycle,
        )
        request_first = RideRequest.query.filter_by(
            public_id=booking_reference, is_deleted=False
        ).first()
        if request_first is not None and request_first.status != "converted":
            from app.transport.services.ride_request_dispatch_service import (
                RideRequestDispatchService, RideRequestDispatchError,
            )
            active_offer = (
                OfferAttempt.query
                .join(SearchCycle, OfferAttempt.cycle_id == SearchCycle.id)
                .filter(
                    SearchCycle.ride_request_id == request_first.id,
                    SearchCycle.status == "searching",
                    OfferAttempt.driver_id == profile.id,
                    OfferAttempt.status == "offered",
                    OfferAttempt.response_deadline > datetime.now(timezone.utc),
                )
                .first()
            )
            if active_offer is None:
                return {
                    "success": False,
                    "error": "This driver has no active offer for the ride",
                    "code": "offer_unavailable",
                }, 409
            try:
                result = RideRequestDispatchService.accept_offer(
                    booking_reference, profile.id, active_offer.vehicle_id,
                    actor=current_user
                )
            except RideRequestDispatchError as e:
                return {"success": False, "error": e.message, "code": e.code}, 409
            except Exception:
                db.session.rollback()
                logger.exception("Request-first driver acceptance failed for %s", booking_reference)
                return {
                    "success": False,
                    "error": "Could not complete the assignment. The request remains trackable.",
                    "code": "assignment_unavailable",
                }, 503
            return {
                "success": True,
                "data": {
                    "booking_reference": booking_reference,
                    "status": "assigned",
                    "offer": "accepted",
                    "payment_status": "pending",
                },
            }

        if request_first is not None:
            # Driver-cancel retry bridge: the request-first request stays
            # "converted" for its ledger, but a driver cancellation closes
            # the linked Booking as no_match and the rider's retry puts it
            # back to confirmed with LEGACY offers. Accept those offers only
            # while the linked Booking is still claimable; anything else
            # keeps the original already-assigned answer.
            linked_booking = Booking.query.filter_by(
                ride_request_id=request_first.id, is_deleted=False
            ).first()
            if (
                linked_booking is None
                or linked_booking.booking_reference != booking_reference
                or linked_booking.status != BookingStatus.CONFIRMED.value
                or linked_booking.assigned_driver_id is not None
            ):
                return {
                    "success": False,
                    "error": "This ride has already been assigned to another driver",
                    "code": "already_accepted",
                }, 409

        vehicle_id = profile.current_vehicle.id if profile.current_vehicle else None
        if not vehicle_id:
            return {
                "success": False,
                "error": "driver has no vehicle to accept with",
            }, 400

        # Offer CAS is the pace gate; the canonical claim is the authority.
        try:
            OfferService.accept_offer(booking_reference, profile.id)
        except DispatchClaimError as e:
            return {
                "success": False,
                "error": e.message,
                "code": e.kind,
            }, 409
        except OfferUnavailableError as e:
            return {"success": False, "error": str(e), "code": "offer_store_unavailable"}, 503

        try:
            result = AssignmentService.claim(
                booking_reference,
                profile.id,
                vehicle_id,
                actor=current_user,
            )
        except DispatchClaimError as e:
            OfferService.cleanup_offer(booking_reference, profile.id)
            return {
                "success": False,
                "error": e.message,
                "code": e.kind,
            }, 409

        return {"success": True, "data": {**result, "offer": "accepted"}}


class DriverOfferDeclineResource(Resource):
    """POST /api/transport/drivers/me/offers/<booking_reference>/decline"""

    @login_required
    def post(self, booking_reference):
        from app.transport.services.offer_service import OfferService
        from app.transport.models import Booking, RideRequest

        profile, error, status = _current_driver_profile()
        if error:
            return error, status
        request_first = RideRequest.query.filter_by(
            public_id=booking_reference, is_deleted=False
        ).first()
        if request_first is not None and request_first.status != "converted":
            from app.transport.services.ride_request_dispatch_service import (
                RideRequestDispatchService,
            )
            declined = RideRequestDispatchService.decline_offer(
                booking_reference, profile.id
            )
            if not declined:
                return {
                    "success": False,
                    "error": "This offer is no longer active",
                    "code": "offer_unavailable",
                }, 409
            return {
                "success": True,
                "data": {"booking_reference": booking_reference, "declined": True},
            }
        if request_first is not None:
            # Same driver-cancel retry bridge as accept: only a still
            # claimable linked Booking may use the legacy offer path.
            linked_booking = Booking.query.filter_by(
                ride_request_id=request_first.id, is_deleted=False
            ).first()
            if (
                linked_booking is None
                or linked_booking.booking_reference != booking_reference
                or linked_booking.status != BookingStatus.CONFIRMED.value
                or linked_booking.assigned_driver_id is not None
            ):
                return {
                    "success": False,
                    "error": "This ride has already been assigned",
                    "code": "already_accepted",
                }, 409
        declined = OfferService.decline_offer(booking_reference, profile.id)
        if not declined:
            return {
                "success": False,
                "error": "This offer is no longer active",
                "code": "offer_unavailable",
            }, 409
        return {
            "success": True,
            "data": {"booking_reference": booking_reference, "declined": True},
        }


# Driver trip lifecycle actions -- single canonical transition table shared by
# BOTH resource variants (internal-id legacy + reference-keyed canonical).
_DRIVER_TRIP_ACTIONS = {
    "en_route": (BookingStatus.ASSIGNED, BookingStatus.DRIVER_EN_ROUTE, "driver_en_route_at", None),
    "arrive": (BookingStatus.DRIVER_EN_ROUTE, BookingStatus.PICKUP_ARRIVED, "driver_arrived_at", None),
    "start": (BookingStatus.PICKUP_ARRIVED, BookingStatus.IN_PROGRESS, None, "pickup_actual_time"),
    "complete": (BookingStatus.IN_PROGRESS, BookingStatus.COMPLETED, "completed_at", "dropoff_actual_time"),
    # CANCEL-FEE-SCHEDULED-P1: special-cased to BookingService.mark_no_show
    # so the 15-minute grace and fee/credit rules stay server-owned.
    "no_show": (BookingStatus.PICKUP_ARRIVED, BookingStatus.NO_SHOW, None, None),
}


def _execute_driver_trip_action(booking, profile, action, actor):
    """Canonical driver-side lifecycle execution (shared by the internal-id
    and reference-keyed trip resources).

    Contract: only the assigned driver may advance; mid-trip transitions use
    guarded UPDATEs (rowcount == 1); completion routes through
    ``AssignmentService.release`` so resources are freed atomically with
    late-release protection. Returns ``(body, http_status_or_None)``.
    """
    from app.transport.services.assignment_service import (
        AssignmentService,
        DispatchClaimError,
    )
    from app.transport.models import LocationLifecycleEvent
    from app.geo.models import LocationObservation

    if action == "cancel":
        # Driver-cancel before trip start: the booking closes as no_match
        # (rider is prompted to search again), never as a paid cancellation.
        # BookingService owns the stage rules, release, audit and rider
        # notification; this resource only maps the outcome.
        from app.transport.services.booking_service import get_booking_service
        from app.utils.exceptions import (
            NotFoundError,
            PermissionError as AppPermissionError,
            ValidationError,
        )

        try:
            result = get_booking_service().driver_cancel(
                booking.id, profile.user_id
            )
            return {
                "success": True,
                "message": result.get("message"),
                "data": result.get("data", {}),
            }, 200
        except NotFoundError as e:
            return {"success": False, "error": str(e)}, 404
        except AppPermissionError as e:
            return {"success": False, "error": str(e)}, 403
        except ValidationError as e:
            return {"success": False, "error": str(e)}, 409

    if action not in _DRIVER_TRIP_ACTIONS:
        return {
            "success": False,
            "error": (
                "action must be one of: "
                "en_route|arrive|start|complete|no_show|cancel"
            ),
        }, 400

    if action == "no_show":
        from app.transport.services.booking_service import get_booking_service
        from app.utils.exceptions import (
            NotFoundError,
            PermissionError as AppPermissionError,
            ValidationError,
        )

        try:
            result = get_booking_service().mark_no_show(
                booking.id, profile.user_id
            )
            return {
                "success": True,
                "message": result.get("message"),
                "data": result.get("data", {}),
            }, 200
        except NotFoundError as e:
            return {"success": False, "error": str(e)}, 404
        except AppPermissionError as e:
            return {"success": False, "error": str(e)}, 403
        except ValidationError as e:
            return {"success": False, "error": str(e)}, 409

    expected, target, ts_col, actual_col = _DRIVER_TRIP_ACTIONS[action]
    now = datetime.now(timezone.utc)
    booking_id = booking.id

    # Helper to capture actual start lifecycle event
    def _capture_actual_start(booking, profile, transition_at):
        """Capture ACTUAL_START lifecycle event referencing closest GEO observation."""
        if not booking.assigned_driver_id:
            return
        # Find the closest existing GEO observation for this driver
        driver_code = profile.driver_code
        if not driver_code:
            return
        obs = LocationObservation.query.filter(
            LocationObservation.entity_type == 'driver',
            LocationObservation.public_ref == driver_code,
            LocationObservation.is_deleted == False,
            LocationObservation.observed_at <= transition_at
        ).order_by(LocationObservation.observed_at.desc()).first()
        
        freshness = "missing"
        age_at_transition = None
        geo_obs_id = None
        reason = "no_observation"
        
        if obs:
            age_at_transition = (transition_at - obs.observed_at).total_seconds()
            geo_obs_id = obs.public_id
            # Freshness threshold - configurable, default 120s
            threshold = 120  # seconds
            if age_at_transition <= threshold:
                freshness = "fresh"
                reason = None
            else:
                freshness = "stale"
                reason = "stale_beyond_threshold"
        
        event = LocationLifecycleEvent(
            booking_id=booking.id,
            endpoint="pickup",
            event_type="ACTUAL_START",
            snapshot=None,  # actual events don't carry snapshot
            geo_observation_public_id=geo_obs_id,
            # Actor is the DRIVER'S USER id (users.id FK) — never the
            # driver-profile id stored on booking.assigned_driver_id.
            actor_user_id=profile.user_id,
            transition_at=transition_at,
            event_metadata={
                "freshness": freshness,
                "age_at_transition": age_at_transition,
                "reason": reason,
                "captured_by": "driver_trip_action_start"
            } if (age_at_transition is not None or freshness == "missing") else {
                "freshness": freshness,
                "reason": reason,
                "captured_by": "driver_trip_action_start"
            }
        )
        db.session.add(event)

    try:
        if action == "start" and target == BookingStatus.IN_PROGRESS:
            # Capture ACTUAL_START at IN_PROGRESS transition
            _capture_actual_start(booking, profile, now)
        
        if target == BookingStatus.COMPLETED:
            booking.completed_at = now
            # Preserve who completed the trip before the canonical release
            # clears the live assignment FKs. This is used only to authorize
            # explicit cash-receipt confirmation after drop-off.
            completion_meta = dict(booking.booking_metadata or {})
            completion_meta["completed_by_driver_profile_id"] = int(profile.id)
            completion_meta["completed_by_driver_code"] = profile.driver_code
            completion_meta["completed_by_user_id"] = int(profile.user_id)
            booking.booking_metadata = completion_meta
            if actual_col:
                setattr(booking, actual_col, now)
            db.session.flush()
            result = AssignmentService.release(
                booking_id,
                BookingStatus.COMPLETED,
                actor=actor,
                audit_extra={"initiator": "driver", "action": action},
            )
        else:
            values = {"status": target.value}
            if ts_col:
                values[ts_col] = now
            if actual_col:
                values[actual_col] = now
            res = db.session.execute(
                sa.update(Booking.__table__)
                .where(
                    Booking.__table__.c.id == booking_id,
                    Booking.__table__.c.assigned_driver_id == profile.id,
                    Booking.__table__.c.status == expected.value,
                    Booking.__table__.c.is_deleted.is_(False),
                )
                .values(**values)
                .execution_options(synchronize_session=False)
            )
            if res.rowcount != 1:
                db.session.rollback()
                return {
                    "success": False,
                    "error": "trip is not in the expected state",
                    "code": "invalid_state",
                }, 409
            db.session.commit()
            db.session.expire_all()
            # FS-1b: trip-action writes must invalidate the booking read
            # cache like claim/release/transition do, otherwise the rider
            # page keeps serving the pre-transition dict until TTL expiry.
            # Best-effort: never fail a committed transition over cache.
            try:
                from app.transport.services import get_booking_service
                get_booking_service()._invalidate_booking_caches(booking_id)
            except Exception:
                logger.warning(
                    "booking read-cache invalidation failed for %s",
                    booking_id, exc_info=True)
            result = {
                "booking_id": booking_id,
                "status": target.value,
                "action": action,
            }

        if action == "complete":
            # The trip is complete independently of payment. Notify Wallet
            # for every currently supported market method: cash becomes due
            # but stays unpaid until the driver's explicit receipt confirmation;
            # Wallet balance collection is performed only inside Wallet.
            refreshed = db.session.get(Booking, booking_id)
            if refreshed is not None:
                method = str(refreshed.payment_method or "").strip().lower()
                if method in ("wallet", "cash"):
                    try:
                        from app.transport.services.payment_service import PaymentService
                        PaymentService.process_payment(
                            booking_id,
                            {
                                "payment_method": method,
                                # Amount and currency are server-derived; never trust
                                # a driver/client supplied settlement amount.
                                "amount": str(
                                    refreshed.final_price or refreshed.total_amount or 0
                                ),
                                "currency": str(getattr(
                                    refreshed.currency, "value", refreshed.currency
                                )),
                            },
                            request_id="trip-complete:%s" % refreshed.booking_reference,
                        )
                    except Exception:
                        db.session.rollback()
                        logger.warning(
                            "Trip %s completed but Wallet settlement/receipt remains pending",
                            refreshed.booking_reference, exc_info=True,
                        )
                db.session.expire_all()
                refreshed = db.session.get(Booking, booking_id)
                if refreshed is not None:
                    result["payment_method"] = refreshed.payment_method
                    result["payment_status"] = str(
                        getattr(refreshed.payment_status, "value", refreshed.payment_status)
                    )
                    result["payment_due_at_trip_end"] = (
                        result["payment_status"].lower() != PaymentStatus.CAPTURED.value
                    )
                    if method == "cash" and result["payment_due_at_trip_end"]:
                        result["payment_instruction"] = (
                            "Confirm cash receipt separately after the rider pays."
                        )
                    elif method not in ("cash", "wallet") and result["payment_due_at_trip_end"]:
                        result["payment_instruction"] = (
                            "Payment remains pending until the selected payment provider confirms settlement."
                        )

        return {"success": True, "data": result}, 200
    except DispatchClaimError as e:
        db.session.rollback()
        return {"success": False, "error": e.message, "code": e.kind}, 409
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error on driver trip action '{action}' for booking {booking_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}, 500


class DriverTripResource(Resource):
    """POST /api/transport/drivers/me/trips/<booking_id>/status

    LEGACY internal-id variant of the driver trip lifecycle endpoint
    (kept for backward compatibility; see BACKLOG active-trip entry).
    Driver-side lifecycle actions for the assigned trip:
      en_route  ASSIGNED            -> DRIVER_EN_ROUTE
      arrive    DRIVER_EN_ROUTE     -> PICKUP_ARRIVED
      start     PICKUP_ARRIVED      -> IN_PROGRESS
      complete  IN_PROGRESS         -> COMPLETED  (canonical release)
    """

    _DRIVER_ACTIONS = _DRIVER_TRIP_ACTIONS

    @login_required
    def post(self, booking_id):
        profile, error, status = _current_driver_profile()
        if error:
            return error, status

        booking = Booking.query.filter_by(id=booking_id, is_deleted=False).first()
        if not booking:
            return {"success": False, "error": "booking not found"}, 404

        if booking.assigned_driver_id != profile.id:
            return {
                "success": False,
                "error": "only the assigned driver may advance this trip",
            }, 403

        data = request.get_json() or {}
        return _execute_driver_trip_action(
            booking, profile, data.get("action"), current_user
        )


class DriverTripReferenceResource(Resource):
    """POST /api/transport/drivers/me/trips/<booking_reference>/status

    CANONICAL reference-keyed variant (BACKLOG active-trip entry /
    AGENTS.md dual-ID law): the workspace's Active Trip quick-action posts
    the public ``booking_reference`` so no internal id crosses into the
    page or the driver-facing API. Same ownership check, same guarded
    transition table, same responses as ``DriverTripResource``.
    """

    _DRIVER_ACTIONS = _DRIVER_TRIP_ACTIONS

    @login_required
    def post(self, booking_reference):
        profile, error, status = _current_driver_profile()
        if error:
            return error, status

        # Serialize concurrent receipt confirmations on the booking row.
        # A second request waits, observes CAPTURED, and returns the idempotent
        # result instead of writing a duplicate payment/audit event.
        booking = Booking.query.filter_by(
            booking_reference=booking_reference, is_deleted=False
        ).with_for_update().first()
        if not booking:
            return {"success": False, "error": "booking not found"}, 404

        if booking.assigned_driver_id != profile.id:
            return {
                "success": False,
                "error": "only the assigned driver may advance this trip",
            }, 403

        data = request.get_json() or {}
        return _execute_driver_trip_action(
            booking, profile, data.get("action"), current_user
        )



class DriverTripPaymentResource(Resource):
    """POST /api/transport/drivers/me/trips/<booking_reference>/payment/confirm-cash.

    Explicit post-trip cash receipt confirmation. Trip completion itself never
    implies that cash was received.
    """

    @login_required
    def post(self, booking_reference):
        from app.transport.models import PaymentStatus
        from app.utils.audit import audit_log

        profile, error, status = _current_driver_profile()
        if error:
            return error, status
        # Hold the booking row until the Wallet receipt and Transport cache
        # are committed together. A duplicate driver tap must observe CAPTURED.
        booking = Booking.query.filter_by(
            booking_reference=booking_reference, is_deleted=False
        ).with_for_update().first()
        if booking is None:
            return {"success": False, "error": "booking not found"}, 404

        metadata = booking.booking_metadata or {}
        completed_by = metadata.get("completed_by_driver_profile_id")
        try:
            completed_by_id = int(completed_by) if completed_by is not None else None
        except (TypeError, ValueError):
            completed_by_id = None
        if completed_by_id is None or completed_by_id != int(profile.id):
            return {
                "success": False,
                "error": "only the driver who completed this trip may confirm its cash receipt",
            }, 403
        if booking.status != BookingStatus.COMPLETED:
            return {"success": False, "error": "cash can be confirmed only after trip completion"}, 409
        if str(booking.payment_method or "").strip().lower() != "cash":
            return {"success": False, "error": "this trip did not select cash payment"}, 409

        receipt = metadata.get("cash_receipt") or {}
        if booking.payment_status == PaymentStatus.CAPTURED:
            if receipt.get("confirmed_by_driver_profile_id") == int(profile.id):
                return {
                    "success": True,
                    "data": {
                        "booking_reference": booking_reference,
                        "payment_status": "captured",
                        "idempotent_replay": True,
                    },
                }, 200
            return {"success": False, "error": "payment is already settled"}, 409
        if booking.payment_status != PaymentStatus.PENDING:
            return {"success": False, "error": "payment is not awaiting cash receipt"}, 409

        now = datetime.now(timezone.utc)
        amount = Decimal(str(booking.final_price or booking.total_amount or 0))
        currency = str(getattr(booking.currency, "value", booking.currency))
        from app.wallet.services.marketplace_invoice_service import (
            MarketplaceInvoiceError,
            MarketplaceInvoiceService,
        )
        try:
            payment_record = (
                BookingPayment.query.filter_by(booking_id=booking.id)
                .order_by(BookingPayment.created_at.desc(), BookingPayment.id.desc())
                .with_for_update()
                .first()
            )
            if payment_record is None:
                payment_record = BookingPayment(
                    booking_id=booking.id,
                    payment_reference="",
                    amount=amount,
                    currency=booking.currency,
                    payment_method="cash",
                    payment_method_details={"timing": "pay_on_completion"},
                    payment_status=PaymentStatus.PENDING,
                    initiated_at=booking.completed_at or now,
                )
                payment_record.generate_payment_reference()
                db.session.add(payment_record)
                db.session.flush()

            # Wallet owns the receipt record. Transport may update its cache only
            # after Wallet accepts the cash receipt for the matching invoice.
            metadata = dict(booking.booking_metadata or {})
            raw_invoice_id = payment_record.wallet_invoice_id or metadata.get("wallet_invoice_id")
            if raw_invoice_id:
                invoice = MarketplaceInvoiceService.get_invoice(
                    raw_invoice_id, for_update=True
                )
            else:
                invoice = MarketplaceInvoiceService.find_invoice(
                    "transport", booking_reference, for_update=True
                )
            if invoice is None:
                invoice = MarketplaceInvoiceService.create_invoice(
                    idempotency_key="transport-booking:%s" % booking.booking_reference,
                    service_code="transport",
                    service_reference=booking.booking_reference,
                    payer_user_id=booking.user_id,
                    amount=amount,
                    currency=currency,
                    payment_method="cash",
                    settlement_timing="pay_on_completion",
                    metadata={"booking_reference": booking.booking_reference},
                    commit=False,
                )

            payment_record.wallet_invoice_id = invoice.id
            metadata["wallet_invoice_id"] = str(invoice.id)
            booking.booking_metadata = metadata
            db.session.add(payment_record)
            db.session.add(booking)

            invoice = MarketplaceInvoiceService.mark_due_after_completion(
                invoice_id=invoice.id,
                payer_user_id=booking.user_id,
                service_code="transport",
                service_reference=booking_reference,
                amount=amount,
                currency=currency,
                commit=False,
            )
            cash_result = MarketplaceInvoiceService.confirm_cash_receipt(
                invoice_id=invoice.id,
                payer_user_id=booking.user_id,
                service_code="transport",
                service_reference=booking_reference,
                amount=amount,
                currency=currency,
                driver_user_id=int(profile.user_id),
                driver_profile_id=int(profile.id),
                driver_code=profile.driver_code,
                commit=False,
            )
            if cash_result.get("status") != "cash_received":
                raise MarketplaceInvoiceError(
                    "cash_receipt_unverified",
                    "Wallet did not confirm the cash receipt.",
                )

            # Refresh the invoice to cache Wallet's canonical receipt result.
            invoice = MarketplaceInvoiceService.get_invoice(invoice.id)
            canonical_receipt = dict(invoice.receipt_metadata or {})
            receipt_cache = {
                "confirmed_by_driver_profile_id": int(canonical_receipt.get("driver_profile_id") or profile.id),
                "confirmed_by_driver_code": canonical_receipt.get("driver_code") or profile.driver_code,
                "confirmed_at": canonical_receipt.get("confirmed_at") or now.isoformat(),
                "amount": str(invoice.amount),
                "currency": invoice.currency,
                "wallet_invoice_id": str(invoice.id),
                "collection_channel": "direct_cash_to_driver",
            }
            metadata = dict(booking.booking_metadata or {})
            metadata["wallet_invoice_id"] = str(invoice.id)
            metadata["wallet_invoice_status"] = invoice.status
            metadata["cash_receipt"] = receipt_cache
            booking.booking_metadata = metadata
            booking.payment_status = PaymentStatus.CAPTURED
            booking.payment_captured_at = invoice.cash_received_at or now
            payment_record.amount = amount
            payment_record.payment_method = "cash"
            payment_record.wallet_invoice_id = invoice.id
            payment_record.payment_status = PaymentStatus.CAPTURED
            payment_record.captured_at = invoice.cash_received_at or now
            payment_record.payment_method_details = {
                **(payment_record.payment_method_details or {}),
                "timing": "pay_on_completion",
                "wallet_invoice_id": str(invoice.id),
                "cash_receipt": receipt_cache,
            }
            db.session.add(booking)
            db.session.add(payment_record)
            db.session.flush()
            audit_log(
                action="transport_cash_payment_received",
                resource_type="booking",
                resource_id=booking.id,
                user_id=current_user.id,
                details={
                    "booking_reference": booking.booking_reference,
                    "payment_method": "cash",
                    "amount": float(amount),
                    "currency": currency,
                    "wallet_invoice_id": str(invoice.id),
                    "confirmed_by_driver_code": profile.driver_code,
                    "confirmed_at": (invoice.cash_received_at or now).isoformat(),
                },
                db_session=db.session,
            )
            db.session.commit()
        except MarketplaceInvoiceError as exc:
            db.session.rollback()
            logger.warning(
                "Wallet rejected cash receipt for %s: %s (%s)",
                booking_reference, exc.message, exc.code,
            )
            return {
                "success": False,
                "error": exc.message,
                "code": exc.code,
            }, 409
        except Exception:
            db.session.rollback()
            logger.exception("Cash receipt confirmation failed for %s", booking_reference)
            return {"success": False, "error": "Could not record cash receipt"}, 503

        try:
            from app.transport.services.booking_service import get_booking_service
            get_booking_service()._invalidate_booking_caches(booking.id)
        except Exception:
            logger.warning("Payment cache invalidation failed for %s", booking_reference, exc_info=True)

        return {
            "success": True,
            "data": {
                "booking_reference": booking_reference,
                "payment_status": "captured",
                "amount": float(booking.final_price or booking.total_amount or 0),
                "currency": str(getattr(booking.currency, "value", booking.currency)),
                "captured_at": now.isoformat(),
            },
        }, 200


class DriverStatusResource(Resource):
    """POST /api/transport/drivers/<int:driver_id>/status

    Self-service driver operational status transition (go-live toggle).

    Contract:
      * ownership     — the authenticated user must own the profile (or be an
                        admin / super_admin / owner).  Denied otherwise: 403.
      * eligibility   — ``can_go_live`` composes the authoritative gates (KYC
                        capability, not-blocked, compliance approved, valid
                        licence, vehicle where the mode requires one).  An
                        attempt to go online while not ready is refused: 403
                        with the checklist so the UI can render the reason.
      * state write   — delegated to ``ProviderService.set_driver_operational_status``
                        (a self-service transition; deliberately does NOT use the
                        obsolete ``driver:update_status`` permission decorator).

    This separation keeps ``can_go_live`` as the single decision authority and
    the service method as the safe execution of an already-authorized change.
    """

    @login_required
    def post(self, driver_id):
        from app.auth.helpers import has_global_role
        from app.transport.services.go_live_service import can_go_live
        from app.transport.services.provider_service import get_provider_service
        from app.utils.exceptions import (
            NotFoundError,
            PermissionError as AppPermissionError,
            ValidationError,
        )

        driver = DriverProfile.query.filter_by(
            id=driver_id, is_deleted=False
        ).first()
        if driver is None:
            return {"success": False, "error": "driver not found"}, 404

        is_admin = has_global_role(current_user, "admin", "super_admin", "owner")
        if driver.user_id != current_user.id and not is_admin:
            return {
                "success": False,
                "error": "not allowed to update this driver's status",
            }, 403

        data = request.get_json(silent=True) or {}
        raw_is_online = data.get("is_online")
        raw_is_available = data.get("is_available")

        if raw_is_online is None and raw_is_available is None:
            return {"success": False, "error": "is_online or is_available required"}, 400

        # Safe boolean parsing
        try:
            is_online = parse_bool(str(raw_is_online)) if raw_is_online is not None else None
            is_available = parse_bool(str(raw_is_available)) if raw_is_available is not None else None
        except ValueError as e:
            return {"success": False, "error": str(e)}, 400

        # SUPPLY-00b: corrected invariant -- is_online => is_available.
        # Refuse the forbidden combination (online without qualification).
        # Project the end state so a partial payload is validated against
        # the resulting state, not just the fields present.
        projected_online = is_online if is_online is not None else driver.is_online
        projected_available = is_available if is_available is not None else driver.is_available
        if projected_online and not projected_available:
            return {
                "success": False,
                "error": "Driver must be available to become online",
            }, 422

        # Eligibility gate: going online is only allowed when can_go_live is
        # ready.  Refuse with a 403 + checklist so the UI can explain why.
        if is_online:
            checklist = can_go_live(driver)
            if not checklist.ready:
                return {
                    "success": False,
                    "error": "driver is not eligible to go live",
                    "go_live": checklist.to_dict(),
                }, 403

        try:
            result = get_provider_service().set_driver_operational_status(
                driver_id=driver_id,
                user_id=current_user.id,
                is_online=is_online,
                is_available=is_available,
            )
            return {"success": True, "data": result["data"]}, 200
        except NotFoundError:
            return {"success": False, "error": "driver not found"}, 404
        except AppPermissionError:
            return {
                "success": False,
                "error": "not allowed to update this driver's status",
            }, 403
        except ValidationError as e:
            return {
                "success": False,
                "error": str(e),
                "go_live": e.details.get("go_live") if getattr(e, "details", None) else None,
            }, 422
        except Exception as e:
            db.session.rollback()
            logger.error(
                f"Error updating driver status for driver {driver_id}: {e}",
                exc_info=True,
            )
            return {"success": False, "error": str(e)}, 500


class DriverVehicleSwitchResource(Resource):
    """POST /api/transport/drivers/<int:driver_id>/vehicles/switch

    Driver self-service vehicle switch (Phase C2, Driver Workspace).

    Contract:
      * ownership     — the authenticated user must own the profile (or be an
                        admin / super_admin / owner).  Denied otherwise: 403.
      * blocked gate  — a self-service switch is refused while the driver is in
                        a blocked compliance state (suspended/revoked/
                        blacklisted); ``can_go_live`` composes that check.
                        Admin may still reassign a blocked driver's vehicle.
      * target vehicle— the switch target MUST be a vehicle the driver owns
                        (``owner_type='driver'``/``owner_id=DriverProfile.id``
                        or ``owner_type='user'``/``owner_id=User.id``) and MUST
                        be ``is_active`` and not soft-deleted.  Admins may
                        pick any active vehicle.
      * state write   — delegated to the canonical ``assign_driver_to_vehicle``
                        (models.py), which ends the driver's current active
                        assignment and any other driver on the target vehicle,
                        then records a new ``DriverVehicleHistory`` row.  This
                        never touches Vehicle ownership columns and preserves
                        the unique active-vehicle partial index.

    The driver may only switch to a vehicle they own: assignment is
    participation, ownership is separate (and unchanged by switching).
    """

    def _profile_or_error(self, driver_id):
        driver = DriverProfile.query.filter_by(
            id=driver_id, is_deleted=False
        ).first()
        if driver is None:
            return None, {"success": False, "error": "driver not found"}, 404
        return driver, None, None

    @login_required
    def post(self, driver_id):
        from app.auth.helpers import has_global_role
        from app.transport.models import Vehicle
        from app.transport.services.go_live_service import can_go_live

        driver, error, status = self._profile_or_error(driver_id)
        if error:
            return error, status

        is_admin = has_global_role(current_user, "admin", "super_admin", "owner")
        if driver.user_id != current_user.id and not is_admin:
            return {
                "success": False,
                "error": "not allowed to switch this driver's vehicle",
            }, 403

        data = request.get_json(silent=True) or {}
        vehicle_id = data.get("vehicle_id")
        if not vehicle_id:
            return {"success": False, "error": "vehicle_id is required"}, 400
        reason = data.get("reason") or "shift_start"

        vehicle = Vehicle.query.filter_by(
            id=vehicle_id, is_deleted=False
        ).first()
        if vehicle is None:
            return {"success": False, "error": "vehicle not found"}, 404

        if not is_admin:
            checklist = can_go_live(driver)
            blocked = next(
                (c for c in checklist.checks if c.key == "blocked"), None
            )
            if blocked is not None and not blocked.ok:
                return {
                    "success": False,
                    "error": "blocked driver cannot switch vehicles",
                    "go_live": checklist.to_dict(),
                }, 403

            owns = (
                (vehicle.owner_type == "driver" and vehicle.owner_id == driver.id)
                or (vehicle.owner_type == "user" and vehicle.owner_id == current_user.id)
            )
            if not owns:
                return {
                    "success": False,
                    "error": "you may only switch to a vehicle you own",
                }, 403

        if vehicle.status != "active":
            return {"success": False, "error": "vehicle is not active"}, 422

        current = driver.current_vehicle
        if current is not None and current.id == vehicle.id:
            return {
                "success": True,
                "data": {
                    "unchanged": True,
                    "assigned_vehicle": {
                        "id": vehicle.id,
                        "license_plate": vehicle.license_plate,
                        "make": vehicle.make,
                        "model": vehicle.model,
                        "year": vehicle.year,
                    },
                    "reason": reason,
                },
            }

        try:
            from app.transport.models import assign_driver_to_vehicle

            assign_driver_to_vehicle(
                driver,
                vehicle,
                reason=reason,
                authorized_by=current_user,
                notes=data.get("notes"),
            )
        except Exception as e:
            db.session.rollback()
            logger.error(
                f"Error switching driver {driver_id} to vehicle {vehicle_id}: {e}",
                exc_info=True,
            )
            return {"success": False, "error": str(e)}, 500

        db.session.refresh(driver)
        assigned = driver.current_vehicle
        return {
            "success": True,
            "data": {
                "unchanged": False,
                "assigned_vehicle": (
                    {
                        "id": assigned.id,
                        "license_plate": assigned.license_plate,
                        "make": assigned.make,
                        "model": assigned.model,
                        "year": assigned.year,
                    }
                    if assigned is not None
                    else None
                ),
                "reason": reason,
            },
        }

# ===========================================================================
# SUPPLY-00 -- admin online override
# ===========================================================================

class DriverAdminOnlineOverrideResource(Resource):
    """POST /api/transport/drivers/<int:driver_id>/admin-online-override

    Authorized-admin control: grant or revoke the per-driver online
    override.  Owner / super_admin / admin / transport_admin only.
    Blocked drivers cannot
    be override-enabled.  All go-live requirement gates (KYC, compliance
    approval, licence, vehicle) are bypassed while the override is active.
    """

    @transport_admin_required
    def post(self, driver_id):
        from app.auth.helpers import has_global_role
        from app.transport.services.provider_service import get_provider_service
        from app.utils.exceptions import (
            NotFoundError as _NotFound,
            ValidationError as _Validation,
        )

        if not has_global_role(current_user, "owner", "super_admin", "admin", "transport_admin"):
            return {"success": False, "error": "not authorized"}, 403

        data = request.get_json(silent=True) or {}
        raw_enabled = data.get("enabled")
        if raw_enabled is None:
            return {"success": False, "error": "enabled is required"}, 400

        # Safe boolean parsing
        try:
            enabled = parse_bool(str(raw_enabled))
        except ValueError as e:
            return {"success": False, "error": str(e)}, 400

        reason = (data.get("reason") or "").strip()[:200]

        try:
            result = get_provider_service().set_admin_online_override(
                driver_id=driver_id,
                enabled=enabled,
                actor_user_id=current_user.id,
                reason=reason,
            )
            return result, 200
        except _NotFound:
            return {"success": False, "error": "driver not found"}, 404
        except _Validation as e:
            return {"success": False, "error": str(e)}, 422
        except Exception as e:
            db.session.rollback()
            logger.error(
                f"admin override error for driver {driver_id}: {e}",
                exc_info=True,
            )
            return {"success": False, "error": "could not set override"}, 500

