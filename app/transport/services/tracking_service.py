#app/transport/services/tracking_service.py
"""
AFCON360 Transport Module - Tracking Service
Handles real-time location tracking and updates
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
import json
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.core.validators import validate_coordinates
from app.extensions import db, redis_client
from app.geo.interfaces import GeoPoint
from app.geo.services import straight_line_distance_m
from app.transport.models import Booking, DriverProfile, Vehicle, BookingStatus
from app.utils.exceptions import ValidationError, NotFoundError
from app.utils.monitoring import monitor_endpoint, record_metric


class TrackingService:
    """Service for real-time tracking"""

    REDIS_PREFIX = "transport:tracking"
    LOCATION_TTL_SECONDS = 300  # 5 minutes freshness boundary

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
                    message=f"Location must include latitude and longitude (required: {required_fields})",
                )

            # Validate coordinate ranges
            validate_coordinates(location_data['latitude'], location_data['longitude'])

            # Prepare location data
            location_update = {
                'latitude': float(location_data['latitude']),
                'longitude': float(location_data['longitude']),
                'accuracy': float(location_data.get('accuracy', 0.0)),
                'speed': float(location_data.get('speed', 0.0)),
                'heading': float(location_data.get('heading', 0.0)),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

            # Store in Redis (resilient to Redis unavailability)
            redis_key = f"{TrackingService.REDIS_PREFIX}:{entity_type}:{entity_id}"
            try:
                redis_client.setex(
                    redis_key,
                    TrackingService.LOCATION_TTL_SECONDS,
                    json.dumps(location_update)
                )
            except Exception as redis_error:
                current_app.logger.warning(f"Redis unavailable during location update: {redis_error}")

            # Update database if entity is driver
            if entity_type == 'driver':
                driver = db.session.get(DriverProfile, entity_id)
                if driver:
                    driver.last_location = location_update
                    driver.location_updated_at = datetime.now(timezone.utc)

                    # Update vehicle location if driver has current vehicle
                    if driver.current_vehicle:
                        driver.current_vehicle.current_location = location_update
                        driver.current_vehicle.last_location_update = datetime.now(timezone.utc)

            # GEO-15 durable history: same-transaction observation append.
            # Every authoritative observation is persisted (no sampling:
            # no product requirement justifies a sampling rule, and each
            # update_location call is already one DB commit, so one extra
            # INSERT is proportional). observed_at is the server-receive
            # timestamp carried by location_update (the producer forwards
            # no trusted device timestamp); recorded_at marks the row
            # write so reads can never refresh history.
            public_ref = TrackingService._public_ref_for(
                entity_type, entity_id)
            if public_ref is not None:
                from app.geo.models import LocationObservation
                db.session.add(LocationObservation(
                    entity_type=entity_type,
                    public_ref=public_ref,
                    latitude=location_update['latitude'],
                    longitude=location_update['longitude'],
                    accuracy=location_update.get('accuracy'),
                    observed_at=datetime.fromisoformat(
                        location_update['timestamp']),
                    source='transport-tracking',
                ))

            db.session.commit()

            # Record metrics
            record_metric('location_updated', tags={'entity_type': entity_type}, value=1)

            # GEO-14 realtime publication (best-effort, scoped channel).
            # Must never break the location write path: every failure
            # mode below degrades to "no live push" while the persisted
            # state above stays authoritative.
            try:
                from app.geo.realtime import (build_location_event,
                                              publish_location_event)
                # public_ref resolved above for the history append; reuse it.
                if public_ref is not None:
                    publish_location_event(
                        redis_client, entity_type, public_ref,
                        build_location_event(entity_type, public_ref,
                                             location_update))
            except Exception as publish_error:
                current_app.logger.debug(
                    "Realtime publication skipped for %s %s: %s",
                    entity_type, entity_id, publish_error)

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
            # Try Redis first (resilient: fall through to the database
            # fallback when Redis is unavailable, mirroring update_location)
            redis_key = f"{TrackingService.REDIS_PREFIX}:{entity_type}:{entity_id}"
            try:
                location_json = redis_client.get(redis_key)
            except Exception as redis_error:
                current_app.logger.warning(
                    f"Redis unavailable during location read: {redis_error}")
                location_json = None

            if location_json:
                location_data = json.loads(location_json)
                source = 'redis'
            else:
                # Fallback to database
                if entity_type == 'driver':
                    driver = db.session.get(DriverProfile, entity_id)
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
            booking = db.session.get(Booking, booking_id)
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
            if booking.assigned_driver_id:
                driver_location = TrackingService.get_location('driver', booking.assigned_driver_id)
                if driver_location['success']:
                    tracking_info['driver_location'] = driver_location['data']['location']

                # Get vehicle location
                if booking.assigned_vehicle_id:
                    vehicle_location = TrackingService.get_location('vehicle', booking.assigned_vehicle_id)
                    if vehicle_location['success']:
                        tracking_info['vehicle_location'] = vehicle_location['data']['location']

            # Calculate estimated arrival
            if tracking_info['driver_location'] and booking.pickup_location:
                distance = TrackingService._calculate_distance(
                    tracking_info['driver_location'],
                    booking.pickup_location
                )
                if distance is not None:
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
    def get_rider_tracking_subject(booking_reference: str,
                                   viewer_user_id: int,
                                   viewer_is_admin: bool) -> Dict[str, Any]:
        """Transport-owned rider-tracking authorization decision (GEO rider node).

        Answers ONLY whether this viewer may observe the assigned
        driver's live location for this booking, and if so which
        driver public reference to stream. GEO delivers; Transport
        decides. Rules (lifecycle §2):
        - unknown/deleted booking -> allowed False, reason unknown_booking
        - non-owner non-admin -> allowed False, reason not_authorized
        - pre-assignment states -> allowed False, reason not_trackable
          (rider sees waiting state, never a candidate driver)
        - active assignment states (canonical ACTIVE_ASSIGNMENT_STATUSES,
          disputed stays latched) + live assignment -> allowed True
        - terminal states, released assignment, missing driver record ->
          allowed False, reason not_trackable / no_driver
        Never raises for bad input; viewer_user_id None is simply
        not the owner.
        """
        from app.transport.services.assignment_service import (
            ACTIVE_ASSIGNMENT_STATUSES)

        if not isinstance(booking_reference, str) or not booking_reference.strip():
            return {"allowed": False, "reason": "unknown_booking",
                    "booking_status": None, "driver_public_ref": None}
        booking = Booking.query.filter_by(
            booking_reference=booking_reference.strip(),
            is_deleted=False).first()
        if booking is None:
            return {"allowed": False, "reason": "unknown_booking",
                    "booking_status": None, "driver_public_ref": None}
        status_value = booking.status.value if hasattr(
            booking.status, "value") else str(booking.status)
        if viewer_user_id != booking.user_id and not viewer_is_admin:
            return {"allowed": False, "reason": "not_authorized",
                    "booking_status": status_value, "driver_public_ref": None}
        if (status_value not in ACTIVE_ASSIGNMENT_STATUSES
                or not booking.assigned_driver_id):
            return {"allowed": False, "reason": "not_trackable",
                    "booking_status": status_value, "driver_public_ref": None}
        driver = db.session.get(DriverProfile, booking.assigned_driver_id)
        if driver is None or getattr(driver, "is_deleted", False):
            return {"allowed": False, "reason": "no_driver",
                    "booking_status": status_value, "driver_public_ref": None}
        public_ref = getattr(driver, "driver_code", None)
        if not public_ref:
            return {"allowed": False, "reason": "no_driver",
                    "booking_status": status_value, "driver_public_ref": None}
        return {"allowed": True, "reason": "trackable",
                "booking_status": status_value,
                "driver_public_ref": str(public_ref)}

    @staticmethod
    def _public_ref_for(entity_type: str, entity_id: int) -> Optional[str]:
        """Public reference for realtime channels (never internal IDs).

        Drivers resolve to `driver_code`, vehicles to `license_plate` —
        the established external references. None when the record does
        not exist (nothing to publish for).
        """
        try:
            if entity_type == 'driver':
                record = db.session.get(DriverProfile, entity_id)
                ref = getattr(record, 'driver_code', None) if record else None
            elif entity_type == 'vehicle':
                record = db.session.get(Vehicle, entity_id)
                ref = getattr(record, 'license_plate', None) if record else None
            else:
                return None
            return str(ref) if ref else None
        except Exception:
            return None

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
        Transport's kilometre contract (nearby filter/sort, ETA heuristic).
        Returns None if either location lacks valid canonical coordinates.
        """
        lat1, lon1 = TrackingService._coordinates_or_none(location1)
        lat2, lon2 = TrackingService._coordinates_or_none(location2)

        if None in (lat1, lon1, lat2, lon2):
            return None

        dist_m = straight_line_distance_m(
            GeoPoint(lat1, lon1), GeoPoint(lat2, lon2))
        return dist_m / 1000.0  # km

    @staticmethod
    def _generate_route_polyline(*locations: Dict) -> str:
        """Generate simplified route polyline"""
        # This is a mock implementation
        # In production, use Google Maps/Mapbox API
        points = []
        for location in locations:
            if location and 'latitude' in location and 'longitude' in location:
                points.append(f"{location['latitude']},{location['longitude']}")

        return "|".join(points) if points else ""

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

            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(seconds=TrackingService.LOCATION_TTL_SECONDS)

            # Get all online drivers
            online_drivers = DriverProfile.query.filter_by(
                is_online=True,
                is_available=True
            ).limit(50).all()

            for driver in online_drivers:
                if not driver.last_location or not driver.location_updated_at:
                    continue
                if driver.location_updated_at < cutoff:
                    continue

                distance = TrackingService._calculate_distance(
                    location,
                    driver.last_location
                )

                if distance is None or distance > radius_km:
                    continue

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

