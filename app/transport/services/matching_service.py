# app/transport/services/matching_service.py
"""
AFCON360 Transport Module - Matching Service
Matches bookings with available drivers/vehicles
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, cast, Tuple
from flask import current_app

from app.extensions import db, cache
from app.geo.interfaces import GeoPoint
from app.geo.services import straight_line_distance_m
from app.transport.models import Booking, DriverProfile, BookingStatus, ProviderType
from app.transport.services import get_provider_service
from app.transport.services.tracking_service import TrackingService
from app.utils.exceptions import ValidationError, NotFoundError
from app.utils.monitoring import monitor_endpoint, record_metric


class MatchingService:
    """Service for matching bookings with providers"""

    CACHE_PREFIX = "transport:matching"

    @staticmethod
    def _booking_vehicle_class(booking: Booking) -> Optional[str]:
        """Canonical vehicle-class preference lives in booking_metadata (JSONB)."""
        meta = cast(Dict[str, Any], booking.booking_metadata or {})
        return meta.get('vehicle_class')

    @staticmethod
    def _driver_vehicle_id(driver: DriverProfile) -> Optional[int]:
        """Resolve the driver's current vehicle id (DriverProfile has no vehicle_id column)."""
        assignment = driver.current_assignment
        if assignment is not None:
            return cast(int, assignment.vehicle_id)
        owned = driver.owned_vehicles or []
        if owned:
            return cast(int, owned[0].id)
        return None

    @staticmethod
    def _ranked_candidates(booking: Booking):
        """pool -> ranker. Returns (available_drivers, ranked_drivers)."""
        provider_service = get_provider_service()
        available_drivers = provider_service.get_available_drivers(
            zone=booking.pickup_location.get('zone'),
            vehicle_class=MatchingService._booking_vehicle_class(booking),
            limit=10
        )
        if not available_drivers:
            return available_drivers, []

        ranked_drivers = MatchingService._rank_drivers_for_booking(
            drivers=available_drivers,
            booking=booking
        )
        return available_drivers, ranked_drivers

    @staticmethod
    @monitor_endpoint("find_driver_for_booking")
    def find_driver_for_booking(booking_id: int) -> Dict[str, Any]:
        """
        Find suitable driver for a booking
        """
        try:
            # Get booking details
            booking = db.session.get(Booking, booking_id)
            if not booking:
                raise NotFoundError(
                    message="Booking not found",
                    resource_type="booking",
                    resource_id=booking_id
                )

            available_drivers, ranked_drivers = MatchingService._ranked_candidates(booking)

            if not available_drivers:
                return {
                    'success': False,
                    'message': 'No available drivers found',
                    'data': {
                        'booking_id': booking_id,
                        'available_drivers': 0
                    }
                }

            if not ranked_drivers:
                return {
                    'success': False,
                    'message': 'No suitable drivers found',
                    'data': {
                        'booking_id': booking_id,
                        'available_drivers': len(available_drivers),
                        'suitable_drivers': 0
                    }
                }

            # Select best driver
            best_driver = ranked_drivers[0]

            # Record metrics
            record_metric(
                'driver_matched',
                tags={
                    'service_type': booking.service_type.value,
                    'vehicle_class': MatchingService._booking_vehicle_class(booking)
                },
                value=1
            )

            return {
                'success': True,
                'message': 'Driver found for booking',
                'data': {
                    'booking_id': booking_id,
                    'driver_id': best_driver['driver_id'],
                    'driver_code': best_driver['driver_code'],
                    'estimated_arrival_time': best_driver.get('estimated_arrival_time', 10),
                    'match_score': best_driver.get('match_score', 0),
                    'total_drivers_considered': len(available_drivers),
                    'ranked_drivers': len(ranked_drivers)
                }
            }

        except NotFoundError:
            raise
        except Exception as e:
            current_app.logger.error(f"Error finding driver for booking: {e}", exc_info=True)
            return {
                'success': False,
                'message': f"Error finding driver: {str(e)}",
                'data': {'booking_id': booking_id}
            }

    @staticmethod
    @monitor_endpoint("discover_and_offer")
    def discover_and_offer(booking_id: int, max_candidates: Optional[int] = None) -> Dict[str, Any]:
        """TH-3-D2: wire the dispatch loop for a booking.

        CONFIRMED+unassigned -> rediscover (pool -> ranker) -> transient offer
        for the top ranked candidate(s). Offers are never authoritative;
        ownership still transfers exclusively through ``AssignmentService.claim``.
        Offer creation degrades safely: any Redis failure leaves the booking
        CONFIRMED/unassigned for rediscovery on the next recovery beat.
        """
        from app.transport.services.offer_service import OfferService, OfferUnavailableError

        try:
            booking = db.session.get(Booking, booking_id)
            if not booking:
                return {'success': False, 'reason': 'booking_not_found', 'offers_created': 0}

            _, ranked_drivers = MatchingService._ranked_candidates(booking)
            if not ranked_drivers:
                return {
                    'success': False,
                    'reason': 'no_suitable_drivers',
                    'offers_created': 0,
                    'ranked_count': 0,
                }

            if max_candidates is None:
                max_candidates = int(
                    current_app.config.get("TRANSPORT_DISPATCH_MAX_CANDIDATES", 3)
                )

            created: List[int] = []
            for candidate in ranked_drivers[:max_candidates]:
                driver_id = candidate.get('driver_id')
                vehicle_id = candidate.get('vehicle_id')
                if not driver_id or not vehicle_id:
                    continue
                try:
                    OfferService.create_offer(booking.booking_reference, driver_id, vehicle_id)
                    created.append(driver_id)
                except OfferUnavailableError:
                    current_app.logger.warning(
                        "dispatch offer creation unavailable for booking %s; "
                        "leaving for rediscovery", booking.booking_reference
                    )
                    break
                except Exception as e:
                    current_app.logger.warning(
                        "dispatch offer creation failed for booking %s: %s",
                        booking.booking_reference, e,
                    )

            return {
                'success': True,
                'offers_created': len(created),
                'driver_ids': created,
                'ranked_count': len(ranked_drivers),
            }
        except Exception as e:
            current_app.logger.error(f"Error discovering/offering booking: {e}", exc_info=True)
            return {'success': False, 'reason': 'error', 'offers_created': 0}

    @staticmethod
    def _rank_drivers_for_booking(drivers: List[Dict[str, Any]], booking: Booking) -> List[Dict[str, Any]]:
        """
        Rank drivers based on suitability for a booking
        """
        now = datetime.now(timezone.utc)
        freshness_cutoff = now - timedelta(seconds=TrackingService.LOCATION_TTL_SECONDS)

        ranked_drivers = []

        for driver in drivers:
            driver_location = driver.get('current_location')
            location_updated_at = driver.get('location_updated_at')

            # Geographic contract: only drivers with a fresh CANONICAL location are matchable.
            # A driver whose location is legacy ('lat'/'lng'), partial, malformed, or
            # out-of-range has no usable geographic position and must be excluded —
            # even if the timestamp is fresh — so non-geographic scoring criteria
            # (rating, acceptance, vehicle class) cannot silently promote them.
            is_matchable = False
            if driver_location and location_updated_at:
                try:
                    updated = datetime.fromisoformat(str(location_updated_at))
                    if updated >= freshness_cutoff:
                        lat, lon = MatchingService._coordinates_or_none(driver_location)
                        is_matchable = lat is not None and lon is not None
                except (TypeError, ValueError):
                    is_matchable = False
            if not is_matchable:
                continue

            score = 0

            # 1. Proximity
            distance = None
            if driver_location and booking.pickup_location:
                distance = MatchingService._calculate_distance(
                    driver_location,
                    booking.pickup_location
                )
                if distance is not None:
                    if distance < 5:
                        score += 30
                    elif distance < 10:
                        score += 20
                    elif distance < 15:
                        score += 10

            # 2. Vehicle class match
            vehicle_classes = driver.get('vehicle_classes', [])
            if MatchingService._booking_vehicle_class(booking) in vehicle_classes:
                score += 25
            elif any(cls in vehicle_classes for cls in ['premium', 'luxury']):
                score += 15
            elif 'van' in vehicle_classes and getattr(booking, 'passenger_count', 1) > 4:
                score += 25

            # 3. Driver rating
            score += int(driver.get('average_rating', 0) * 4)

            # 4. Acceptance rate
            score += int(driver.get('acceptance_rate', 100) / 100 * 15)

            # 5. Service type experience
            service_types = driver.get('service_types', [])
            if booking.service_type.value in service_types:
                score += 10

            # Estimated arrival time
            if distance is not None:
                estimated_arrival = distance * 2 + 5
            else:
                estimated_arrival = 15

            # Add driver if minimum score met
            if score >= 40:
                driver['match_score'] = score
                driver['estimated_arrival_time'] = estimated_arrival
                ranked_drivers.append(driver)

        ranked_drivers.sort(key=lambda x: x.get('match_score', 0), reverse=True)
        return ranked_drivers

    @staticmethod
    def _coordinates_or_none(location: Dict) -> Tuple[Optional[float], Optional[float]]:
        """Return (lat, lon) floats only when BOTH canonical values are valid, else (None, None)."""
        try:
            latitude = location.get('latitude')
            longitude = location.get('longitude')
            if latitude is None or longitude is None:
                return None, None
            lat = float(latitude)
            lon = float(longitude)
            if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                return None, None
            return lat, lon
        except (TypeError, ValueError, AttributeError):
            return None, None

    @staticmethod
    def _calculate_distance(location1: Dict, location2: Dict) -> Optional[float]:
        """Distance between two locations in kilometres.

        Generic math is owned by canonical GEO (radians-correct haversine,
        metres); this boundary converts metres → km to preserve
        Transport's kilometre contract (proximity bands, ETA heuristic).
        Returns None if either location lacks valid canonical coordinates.
        """
        lat1, lon1 = MatchingService._coordinates_or_none(location1)
        lat2, lon2 = MatchingService._coordinates_or_none(location2)

        if None in (lat1, lon1, lat2, lon2):
            return None

        dist_m = straight_line_distance_m(
            GeoPoint(lat1, lon1), GeoPoint(lat2, lon2))
        return dist_m / 1000.0  # km

    @staticmethod
    @monitor_endpoint("assign_driver_to_booking")
    def assign_driver_to_booking(booking_id: int, driver_id: int, force_assignment: bool = False) -> Dict[str, Any]:
        """Assign a driver to a booking (TH-3-D2).

        DEPRECATED legacy entry point with no known callers. It now
        DELEGATES to the canonical dispatch claim so no legacy path can
        bypass atomic assignment guarantees. ``force_assignment`` maps to the
        admin-only ``force`` flag of the claim.
        """
        from app.transport.services.assignment_service import (
            AssignmentService,
            DispatchClaimError,
        )

        try:
            booking = db.session.get(Booking, booking_id)
            if not booking:
                raise NotFoundError("Booking not found", resource_type="booking", resource_id=booking_id)

            driver = db.session.get(DriverProfile, driver_id)
            if not driver:
                raise NotFoundError("Driver not found", resource_type="driver", resource_id=driver_id)

            driver_vehicle_id = MatchingService._driver_vehicle_id(driver)
            if not driver_vehicle_id:
                raise ValidationError(
                    message=f"Driver has no vehicle assigned (driver_id={driver_id})",
                )

            result = AssignmentService.claim(
                booking.booking_reference,
                driver_id,
                driver_vehicle_id,
                actor=None,
                force=bool(force_assignment),
            )

            db.session.expire_all()
            booking = db.session.get(Booking, booking_id)

            record_metric('driver_assigned', tags={'booking_id': booking_id}, value=1)

            return {
                'success': True,
                'message': 'Driver assigned to booking',
                'data': {
                    'booking_id': booking_id,
                    'driver_id': driver_id,
                    'vehicle_id': driver_vehicle_id,
                    'booking_status': booking.status.value if booking else result['status'],
                }
            }

        except DispatchClaimError as e:
            db.session.rollback()
            raise ValidationError(message=e.message)
        except (NotFoundError, ValidationError):
            db.session.rollback()
            raise
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error assigning driver: {e}", exc_info=True)
            raise


# ------------------------
# Singleton getter
# ------------------------
from threading import Lock

_matching_service_instance = None
_matching_service_lock = Lock()

def get_matching_service():
    """Singleton getter for MatchingService"""
    global _matching_service_instance
    if _matching_service_instance is None:
        with _matching_service_lock:
            if _matching_service_instance is None:
                _matching_service_instance = MatchingService()
    return _matching_service_instance

