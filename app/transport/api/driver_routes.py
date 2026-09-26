# app/transport/api/driver_routes.py
from flask import request
from flask_restful import Resource
from flask_login import current_user, login_required
from app.extensions import db
from app.transport.models import DriverProfile, DriverVehicleHistory, Booking, BookingStatus
from app.auth.decorators import admin_required
from app.transport.utils.helpers import paginate, filter_query, sort_query
from datetime import datetime, timedelta, timezone
from sqlalchemy import or_, func
import sqlalchemy as sa
import logging

logger = logging.getLogger(__name__)

# Fields allowed for sorting - prevents arbitrary column injection
DRIVER_SORT_FIELDS = [
    "created_at", "updated_at", "average_rating",
    "reliability_score", "safety_score", "total_trips",
    "compliance_status", "verification_tier"
]


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
        # Filter via helpers
        # ------------------------------------------------------------------
        filters = {
            "verification_tier":  request.args.get("verification_tier"),
            "compliance_status":  request.args.get("compliance_status"),
            "is_online":          request.args.get("is_online", type=bool),
            "is_available":       request.args.get("is_available", type=bool),
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

        try:
            driver = DriverProfile(
                user_id=data.get("user_id"),
                driver_code=data.get("driver_code"),
                license_number=data.get("license_number"),
                languages_spoken=data.get("languages_spoken", ["en"]),
                vehicle_classes=data.get("vehicle_classes", ["comfort"]),
                service_types=data.get("service_types", ["on_demand"]),
                max_passenger_capacity=data.get("max_passenger_capacity", 4),
                max_luggage_capacity=data.get("max_luggage_capacity", 2),
                commission_rate=data.get("commission_rate", 15.00),
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
            return {"success": False, "error": str(e)}, 500


class DriverDetailResource(Resource):
    """GET/PUT/DELETE /api/transport/drivers/<int:driver_id>"""

    @admin_required
    def get(self, driver_id):
        """Get single driver with full detail"""
        driver = DriverProfile.query.get_or_404(driver_id)

        recent_trips = (
            Booking.query
            .filter_by(assigned_driver_id=driver_id, is_deleted=False)
            .order_by(Booking.created_at.desc())
            .limit(10)
            .all()
        )

        total_earnings = (
            db.session.query(func.sum(Booking.final_price))
            .filter(
                Booking.assigned_driver_id == driver_id,
                Booking.payment_status == "captured",
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

    @admin_required
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
        driver = DriverProfile.query.get_or_404(driver_id)
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
            return {"success": False, "error": str(e)}, 500


class DriverVerificationResource(Resource):
    """POST /api/transport/drivers/<int:driver_id>/verification"""

    @admin_required
    def post(self, driver_id):
        """Update driver verification status"""
        driver = DriverProfile.query.get_or_404(driver_id)
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        action = data.get("action")

        if action == "verify_license":
            driver.license_verified = True
            driver.license_verified_at = datetime.now(timezone.utc)
            driver.license_verified_by = data.get("verified_by")

        elif action == "verify_police":
            driver.police_clearance_verified = True
            driver.police_clearance_date = datetime.now(timezone.utc)
            driver.background_check_reference = data.get("reference")

        elif action == "verify_tier":
            driver.verification_tier = data.get("tier")

        elif action == "update_compliance":
            driver.compliance_status = data.get("status")

        else:
            return {"success": False, "error": f"Unknown action: {action}"}, 400

        try:
            db.session.commit()
            logger.info(f"Driver {driver_id} verification updated: action={action}")
            return {
                "success": True,
                "data": driver.to_dict(exclude=["license_number_encrypted"]),
            }
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating verification for driver {driver_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


class DriverLocationResource(Resource):
    """GET/POST /api/transport/drivers/<int:driver_id>/location"""

    @admin_required
    def get(self, driver_id):
        """Get driver's last known location"""
        driver = DriverProfile.query.get_or_404(driver_id)
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
        """Update driver location (mobile app) — canonical TrackingService path.

        TH-3-D2 security gate: only the driver who owns the profile (or an
        admin) may publish a location for it.
        """
        from app.auth.helpers import has_global_role

        driver = DriverProfile.query.get_or_404(driver_id)
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

        if "latitude" not in data or "longitude" not in data:
            return {"success": False, "error": "latitude and longitude are required"}, 400

        try:
            from app.transport.services.tracking_service import get_tracking_service
            from app.utils.exceptions import ValidationError
            tracking_service = get_tracking_service()
            result = tracking_service.update_location('driver', driver.id, {
                'latitude': data.get('latitude'),
                'longitude': data.get('longitude'),
                'accuracy': data.get('accuracy', 0.0),
                'speed': data.get('speed', 0.0),
                'heading': data.get('heading', 0.0),
            })

            driver.last_seen_at = datetime.now(timezone.utc)
            db.session.commit()

            if not result.get('success'):
                return {"success": False, "error": result.get('message', 'Location update failed')}, 500

            return {"success": True, "data": {"location": result['data']['location']}}
        except ValidationError as e:
            db.session.rollback()
            return {"success": False, "error": str(e)}, 400
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating location for driver {driver_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


class DriverHistoryResource(Resource):
    """GET /api/transport/drivers/<int:driver_id>/history"""

    @admin_required
    def get(self, driver_id):
        """Get driver's vehicle assignment history"""
        DriverProfile.query.get_or_404(driver_id)  # 404 if driver doesn't exist

        days = min(request.args.get("days", 30, type=int), 365)  # cap at 1 year
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

        profile, error, status = _current_driver_profile()
        if error:
            return error, status
        offers = OfferService.list_driver_offers(profile.id)
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

        profile, error, status = _current_driver_profile()
        if error:
            return error, status
        declined = OfferService.decline_offer(booking_reference, profile.id)
        return {
            "success": True,
            "data": {"booking_reference": booking_reference, "declined": declined},
        }


# Driver trip lifecycle actions -- single canonical transition table shared by
# BOTH resource variants (internal-id legacy + reference-keyed canonical).
_DRIVER_TRIP_ACTIONS = {
    "en_route": (BookingStatus.ASSIGNED, BookingStatus.DRIVER_EN_ROUTE, "driver_en_route_at"),
    "arrive": (BookingStatus.DRIVER_EN_ROUTE, BookingStatus.PICKUP_ARRIVED, "driver_arrived_at"),
    "start": (BookingStatus.PICKUP_ARRIVED, BookingStatus.IN_PROGRESS, None),
    "complete": (BookingStatus.IN_PROGRESS, BookingStatus.COMPLETED, "completed_at"),
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

    if action not in _DRIVER_TRIP_ACTIONS:
        return {
            "success": False,
            "error": "action must be one of: en_route|arrive|start|complete",
        }, 400

    expected, target, ts_col = _DRIVER_TRIP_ACTIONS[action]
    now = datetime.now(timezone.utc)
    booking_id = booking.id

    try:
        if target == BookingStatus.COMPLETED:
            booking.completed_at = now
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
            result = {
                "booking_id": booking_id,
                "status": target.value,
                "action": action,
            }

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

        booking = Booking.query.filter_by(
            booking_reference=booking_reference, is_deleted=False
        ).first()
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
        is_online = data.get("is_online")
        is_available = data.get("is_available")

        if is_online is None and is_available is None:
            return {"success": False, "error": "is_online or is_available required"}, 400

        if is_online is not None:
            is_online = bool(is_online)
        if is_available is not None:
            is_available = bool(is_available)

        if is_available and not is_online:
            return {
                "success": False,
                "error": "Driver must be online to become available",
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
