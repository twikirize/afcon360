#app/transport/services/tracking_service.py
"""
AFCON360 Transport Module - Tracking Service
Handles real-time location tracking and updates
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
import json
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db, redis_client
from app.transport.models import Booking, DriverProfile, Vehicle, BookingStatus
from app.utils.exceptions import ValidationError, NotFoundError
from app.utils.monitoring import monitor_endpoint, record_metric


class TrackingService:
    """Service for real-time tracking"""

    REDIS_PREFIX = "transport:tracking"

    @staticmethod
    @monitor_endpoint("update_location")
    def update_location(entity_type: str, entity_id: int,
                        location_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update location for an entity (driver/vehicle)

        Args:
            entity_type: 'driver' or 'vehicle'
            entity_id: ID of entity
            location_data: Location information

        Returns:
            Update result
        """
        try:
            # Validate location data
            required_fields = ['latitude', 'longitude']
            if not all(field in location_data for field in required_fields):
                raise ValidationError(
                    message="Location must include latitude and longitude",
                    details={'required_fields': required_fields},
                    code="INVALID_LOCATION_DATA"
                )

            # Prepare location data
            location_update = {
                'latitude': float(location_data['latitude']),
                'longitude': float(location_data['longitude']),
                'accuracy': float(location_data.get('accuracy', 0.0)),
                'speed': float(location_data.get('speed', 0.0)),
                'heading': float(location_data.get('heading', 0.0)),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

            # Store in Redis
            redis_key = f"{TrackingService.REDIS_PREFIX}:{entity_type}:{entity_id}"
            redis_client.setex(
                redis_key,
                300,  # 5 minutes TTL
                json.dumps(location_update)
            )

            # Update database if entity is driver
            if entity_type == 'driver':
                driver = DriverProfile.query.get(entity_id)
                if driver:
                    driver.last_location = location_update
                    driver.location_updated_at = datetime.now(timezone.utc)

                    # Update vehicle location if driver has current vehicle
                    if driver.current_vehicle:
                        driver.current_vehicle.current_location = location_update
                        driver.current_vehicle.last_location_update = datetime.now(timezone.utc)

                    db.session.commit()

            # Record metrics
            record_metric('location_updated', tags={'entity_type': entity_type}, value=1)

            return {
                'success': True,
                'message': 'Location updated successfully',
                'data': {
                    'entity_type': entity_type,
                    'entity_id': entity_id,
                    'location': location_update
                }
            }

        except ValidationError as e:
            raise

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error updating location: {e}", exc_info=True)
            return {
                'success': False,
                'message': f"Error updating location: {str(e)}",
                'data': {'entity_type': entity_type, 'entity_id': entity_id}
            }
        except Exception as e:
            current_app.logger.error(f"Error updating location: {e}", exc_info=True)
            return {
                'success': False,
                'message': f"Error updating location: {str(e)}",
                'data': {'entity_type': entity_type, 'entity_id': entity_id}
            }

    @staticmethod
    @monitor_endpoint("get_location")
    def get_location(entity_type: str, entity_id: int) -> Dict[str, Any]:
        """Get current location of an entity"""
        try:
            # Try Redis first
            redis_key = f"{TrackingService.REDIS_PREFIX}:{entity_type}:{entity_id}"
            location_json = redis_client.get(redis_key)

            if location_json:
                location_data = json.loads(location_json)
                source = 'redis'
            else:
                # Fallback to database
                if entity_type == 'driver':
                    driver = DriverProfile.query.get(entity_id)
                    if driver and driver.last_location:
                        location_data = driver.last_location
                        source = 'database'
                    else:
                        raise NotFoundError(
                            message="Location not found",
                            resource_type=f"{entity_type}_location",
                            resource_id=entity_id
                        )
                else:
                    location_data = None
                    source = 'not_found'

            if location_data:
                return {
                    'success': True,
                    'data': {
                        'entity_type': entity_type,
                        'entity_id': entity_id,
                        'location': location_data,
                        'source': source,
                        'timestamp': location_data.get('timestamp')
                    }
                }
            else:
                raise NotFoundError(
                    message="Location not found",
                    resource_type=f"{entity_type}_location",
                    resource_id=entity_id
                )

        except NotFoundError:
            raise
        except Exception as e:
            current_app.logger.error(f"Error getting location: {e}", exc_info=True)
            return {
                'success': False,
                'message': f"Error getting location: {str(e)}",
                'data': {'entity_type': entity_type, 'entity_id': entity_id}
            }

    @staticmethod
    @monitor_endpoint("track_booking")
    def track_booking(booking_id: int) -> Dict[str, Any]:
        """Get tracking information for a booking"""
        try:
            booking = Booking.query.get(booking_id)
            if not booking:
                raise NotFoundError(
                    message="Booking not found",
                    resource_type="booking",
                    resource_id=booking_id
                )

            tracking_info = {
                'booking_id': booking_id,
                'status': booking.status.value,
                'pickup_location': booking.pickup_location,
                'dropoff_location': booking.dropoff_location,
                'driver_location': None,
                'vehicle_location': None,
                'estimated_arrival': None,
                'route_polyline': None
            }

            # Get driver location if assigned
            if booking.driver_id:
                driver_location = TrackingService.get_location('driver', booking.driver_id)
                if driver_location['success']:
                    tracking_info['driver_location'] = driver_location['data']['location']

                # Get vehicle location
                if booking.vehicle_id:
                    vehicle_location = TrackingService.get_location('vehicle', booking.vehicle_id)
                    if vehicle_location['success']:
                        tracking_info['vehicle_location'] = vehicle_location['data']['location']

            # Calculate estimated arrival
            if tracking_info['driver_location'] and booking.pickup_location:
                distance = TrackingService._calculate_distance(
                    tracking_info['driver_location'],
                    booking.pickup_location
                )
                tracking_info['estimated_arrival'] = distance * 2  # 2 mins per km

            # Generate route polyline (simplified)
            if (tracking_info['driver_location'] and
                    booking.pickup_location and
                    booking.dropoff_location):
                tracking_info['route_polyline'] = TrackingService._generate_route_polyline(
                    tracking_info['driver_location'],
                    booking.pickup_location,
                    booking.dropoff_location
                )

            return {
                'success': True,
                'data': tracking_info
            }

        except NotFoundError:
            raise
        except Exception as e:
            current_app.logger.error(f"Error tracking booking: {e}", exc_info=True)
            return {
                'success': False,
                'message': f"Error tracking booking: {str(e)}",
                'data': {'booking_id': booking_id}
            }

    @staticmethod
    def _calculate_distance(location1: Dict, location2: Dict) -> float:
        """Calculate distance between two locations"""
        try:
            import math

            lat1 = location1.get('latitude', 0)
            lon1 = location1.get('longitude', 0)
            lat2 = location2.get('latitude', 0)
            lon2 = location2.get('longitude', 0)

            # Convert to radians
            lat1_rad = math.radians(lat1)
            lon1_rad = math.radians(lon1)
            lat2_rad = math.radians(lat2)
            lon2_rad = math.radians(lon2)

            # Haversine formula
            dlon = lon2_rad - lon1_rad
            dlat = lat2_rad - lat1_rad

            a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
            c = 2 * math.asin(math.sqrt(a))

            # Earth radius in km
            r = 6371

            return c * r

        except:
            # Fallback simple calculation
            lat_diff = abs(location1.get('latitude', 0) - location2.get('latitude', 0))
            lon_diff = abs(location1.get('longitude', 0) - location2.get('longitude', 0))
            return math.sqrt(lat_diff ** 2 + lon_diff ** 2) * 111

    @staticmethod
    def _generate_route_polyline(*locations: Dict) -> str:
        """Generate simplified route polyline"""
        # This is a mock implementation
        # In production, use Google Maps/Mapbox API
        points = []
        for location in locations:
            if location and 'latitude' in location and 'longitude' in location:
                points.append(f"{location['latitude']},{location['longitude']}")

        return "|".join(points) if points else None

    @staticmethod
    @monitor_endpoint("get_nearby_drivers")
    def get_nearby_drivers(location: Dict[str, float],
                           radius_km: float = 5,
                           limit: int = 10) -> List[Dict[str, Any]]:
        """Get drivers near a location"""
        try:
            # This is a simplified implementation
            # In production, use Redis GEO commands or spatial database

            nearby_drivers = []

            # Get all online drivers
            online_drivers = DriverProfile.query.filter_by(
                is_online=True,
                is_available=True
            ).limit(50).all()

            for driver in online_drivers:
                if driver.last_location:
                    distance = TrackingService._calculate_distance(
                        location,
                        driver.last_location
                    )

                    if distance <= radius_km:
                        driver_data = {
                            'driver_id': driver.id,
                            'driver_code': driver.driver_code,
                            'distance_km': distance,
                            'location': driver.last_location,
                            'vehicle_class': driver.vehicle_classes[0] if driver.vehicle_classes else 'comfort',
                            'rating': float(driver.average_rating) if driver.average_rating else 0.0
                        }
                        nearby_drivers.append(driver_data)

            # Sort by distance
            nearby_drivers.sort(key=lambda x: x['distance_km'])

            return nearby_drivers[:limit]

        except Exception as e:
            current_app.logger.error(f"Error getting nearby drivers: {e}", exc_info=True)
            return []
# ------------------------
# Singleton getter (module-level)
# ------------------------
from threading import Lock

_tracking_service_instance = None
_tracking_service_lock = Lock()

def get_tracking_service():
    """Singleton getter for TrackingService"""
    global _tracking_service_instance
    if _tracking_service_instance is None:
        with _tracking_service_lock:
            if _tracking_service_instance is None:
                _tracking_service_instance = TrackingService()
    return _tracking_service_instance
