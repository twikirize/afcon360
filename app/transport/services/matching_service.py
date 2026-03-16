# app/transport/services/matching_service.py
"""
AFCON360 Transport Module - Matching Service
Matches bookings with available drivers/vehicles
"""

from datetime import datetime, timezone
from typing import Dict, List, Any
import math
from flask import current_app

from app.extensions import db, cache
from app.transport.models import Booking, DriverProfile, BookingStatus
from app.transport.services import get_provider_service
from app.utils.exceptions import ValidationError, NotFoundError
from app.utils.monitoring import monitor_endpoint, record_metric


class MatchingService:
    """Service for matching bookings with providers"""

    CACHE_PREFIX = "transport:matching"

    @staticmethod
    @monitor_endpoint("find_driver_for_booking")
    def find_driver_for_booking(booking_id: int) -> Dict[str, Any]:
        """
        Find suitable driver for a booking
        """
        try:
            # Get booking details
            booking = Booking.query.get(booking_id)
            if not booking:
                raise NotFoundError(
                    message="Booking not found",
                    resource_type="booking",
                    resource_id=booking_id
                )

            # Get available drivers via singleton provider service
            provider_service = get_provider_service()
            available_drivers = provider_service.get_available_drivers(
                zone=booking.pickup_location.get('zone'),
                vehicle_class=booking.vehicle_class_preference,
                limit=10
            )

            if not available_drivers:
                return {
                    'success': False,
                    'message': 'No available drivers found',
                    'data': {
                        'booking_id': booking_id,
                        'available_drivers': 0
                    }
                }

            # Score and rank drivers
            ranked_drivers = MatchingService._rank_drivers_for_booking(
                drivers=available_drivers,
                booking=booking
            )

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
                    'vehicle_class': booking.vehicle_class_preference
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
    def _rank_drivers_for_booking(drivers: List[Dict[str, Any]], booking: Booking) -> List[Dict[str, Any]]:
        """
        Rank drivers based on suitability for a booking
        """
        ranked_drivers = []

        for driver in drivers:
            score = 0

            # 1. Proximity
            if driver.get('current_location') and booking.pickup_location:
                distance = MatchingService._calculate_distance(
                    driver['current_location'],
                    booking.pickup_location
                )
                if distance < 5:
                    score += 30
                elif distance < 10:
                    score += 20
                elif distance < 15:
                    score += 10

            # 2. Vehicle class match
            vehicle_classes = driver.get('vehicle_classes', [])
            if booking.vehicle_class_preference in vehicle_classes:
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
            if driver.get('current_location') and booking.pickup_location:
                distance = MatchingService._calculate_distance(driver['current_location'], booking.pickup_location)
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
    def _calculate_distance(location1: Dict, location2: Dict) -> float:
        """Calculate distance between two locations"""
        try:
            lat1 = math.radians(location1.get('latitude', 0))
            lon1 = math.radians(location1.get('longitude', 0))
            lat2 = math.radians(location2.get('latitude', 0))
            lon2 = math.radians(location2.get('longitude', 0))

            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
            c = 2 * math.asin(math.sqrt(a))
            return 6371 * c  # km
        except Exception:
            lat_diff = abs(location1.get('latitude', 0) - location2.get('latitude', 0))
            lon_diff = abs(location1.get('longitude', 0) - location2.get('longitude', 0))
            return math.sqrt(lat_diff ** 2 + lon_diff ** 2) * 111

    @staticmethod
    @monitor_endpoint("assign_driver_to_booking")
    def assign_driver_to_booking(booking_id: int, driver_id: int, force_assignment: bool = False) -> Dict[str, Any]:
        """Assign a driver to a booking"""
        try:
            booking = Booking.query.get(booking_id)
            if not booking:
                raise NotFoundError("Booking not found", resource_type="booking", resource_id=booking_id)

            driver = DriverProfile.query.get(driver_id)
            if not driver:
                raise NotFoundError("Driver not found", resource_type="driver", resource_id=driver_id)

            if not driver.is_available and not force_assignment:
                raise ValidationError(
                    message="Driver is not available",
                    details={'driver_id': driver_id, 'is_available': False},
                    code="DRIVER_NOT_AVAILABLE"
                )

            if not driver.vehicle_id:
                raise ValidationError(
                    message="Driver has no vehicle assigned",
                    details={'driver_id': driver_id},
                    code="NO_VEHICLE_ASSIGNED"
                )

            # Update booking
            booking.driver_id = driver_id
            booking.vehicle_id = driver.vehicle_id
            booking.provider_type = 'user'
            booking.provider_id = driver_id
            booking.status = BookingStatus.CONFIRMED
            booking.confirmed_at = datetime.now(timezone.utc)

            # Update driver
            driver.is_available = False
            driver.current_booking_id = booking_id

            db.session.commit()

            # Invalidate caches
            cache.delete(f"booking:{booking_id}")
            cache.delete(f"driver:{driver_id}")

            record_metric('driver_assigned', tags={'booking_id': booking_id}, value=1)

            return {
                'success': True,
                'message': 'Driver assigned to booking',
                'data': {
                    'booking_id': booking_id,
                    'driver_id': driver_id,
                    'vehicle_id': driver.vehicle_id,
                    'booking_status': booking.status.value
                }
            }

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
