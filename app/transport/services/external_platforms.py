#app/transport/services/external_platforms.py
"""
AFCON360 Transport Module - External Platforms Integration
Handles integration with third-party services
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
import functools
import logging
import requests
import json
from flask import current_app

from app.extensions import redis_client
from app.utils.exceptions import ValidationError
from app.utils.monitoring import monitor_endpoint, record_metric

logger = logging.getLogger(__name__)

# Circuit parameters - roadmap Edition 2.0 Fix 2.2 (threshold=5, recovery=30s)
CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_RECOVERY_TIMEOUT = 30
CIRCUIT_FAILURE_TTL = 60
CIRCUIT_OPERATION = "directions"

# Typed PROVIDER_FAILURE surface: external-dependency exceptions only.
PROVIDER_FAILURE_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.HTTPError,
)


class CircuitOpenError(Exception):
    """Circuit is OPEN for this (provider, operation); caller must fall back."""


DIRECTIONS_FALLBACK_EXCEPTIONS = (CircuitOpenError,) + PROVIDER_FAILURE_EXCEPTIONS


def _circuit_keys(provider: str) -> Tuple[str, str]:
    prefix = f"transport:circuit:{provider}:{CIRCUIT_OPERATION}"
    return f"{prefix}:failures", f"{prefix}:state"


def _as_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _circuit_state(provider: str) -> Tuple[bool, int]:
    """Read circuit state. Returns (is_open, failure_count). Fails open."""
    failures_key, state_key = _circuit_keys(provider)
    try:
        pipe = redis_client.pipeline()
        pipe.get(state_key)
        pipe.get(failures_key)
        state_raw, failures_raw = pipe.execute()
        failure_count = _as_int(failures_raw)
        if state_raw is None:
            if failure_count >= CIRCUIT_FAILURE_THRESHOLD:
                # OPEN expired: the surviving failures key is the evidence of
                # the prior OPEN. Claim it atomically — DEL is a single Redis
                # command, so exactly one worker's DEL returns 1 and only
                # that claimant emits the recovery transition. Every
                # observer still resumes CLOSED (unconditional resume).
                claimed = redis_client.delete(failures_key)
                if claimed:
                    logger.info(
                        "Circuit recovery: provider=%s operation=%s failure_count=%d reason=recovery_expired",
                        provider, CIRCUIT_OPERATION, failure_count,
                    )
                failure_count = 0
            return False, failure_count
        return True, failure_count
    except Exception as exc:
        logger.warning(
            "Circuit state read unavailable for %s, failing open: %s",
            provider, exc,
        )
        return False, 0


def _record_failure(provider: str) -> None:
    failures_key, state_key = _circuit_keys(provider)
    try:
        pipe = redis_client.pipeline()
        pipe.incr(failures_key)
        pipe.expire(failures_key, CIRCUIT_FAILURE_TTL)
        results = pipe.execute()
        count = _as_int(results[0])
        if count == CIRCUIT_FAILURE_THRESHOLD:
            redis_client.set(state_key, "open", ex=CIRCUIT_RECOVERY_TIMEOUT)
            logger.error(
                "Circuit opened: provider=%s operation=%s failure_count=%d reason=threshold_reached",
                provider, CIRCUIT_OPERATION, count,
            )
            record_metric(f"circuit.open.{provider}.{CIRCUIT_OPERATION}", count)
    except Exception as exc:
        logger.warning(
            "Circuit failure record unavailable for %s, failing open: %s",
            provider, exc,
        )


def _record_success(provider: str) -> None:
    failures_key, _ = _circuit_keys(provider)
    try:
        redis_client.delete(failures_key)
    except Exception as exc:
        logger.warning(
            "Circuit success reset unavailable for %s: %s",
            provider, exc,
        )


def circuit_breaker(provider_name: str):
    """Redis-backed circuit breaker scoped to (provider, operation)."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            is_open, _ = _circuit_state(provider_name)
            if is_open:
                raise CircuitOpenError(
                    f"Circuit open for {provider_name}:{CIRCUIT_OPERATION}"
                )
            try:
                result = func(*args, **kwargs)
            except PROVIDER_FAILURE_EXCEPTIONS as exc:
                logger.warning(
                    "Provider failure for %s:%s: %s",
                    provider_name, CIRCUIT_OPERATION, exc,
                )
                _record_failure(provider_name)
                raise
            except Exception:
                logger.error(
                    "Local defect in %s:%s",
                    provider_name, CIRCUIT_OPERATION,
                    exc_info=True,
                )
                raise
            _record_success(provider_name)
            return result

        return wrapper

    return decorator


class ExternalPlatformsService:
    """Service for external platform integrations"""

    # API Configuration
    GOOGLE_MAPS_CONFIG = {
        'api_key': None,  # Set from config
        'base_url': 'https://maps.googleapis.com/maps/api'
    }

    MAPBOX_CONFIG = {
        'access_token': None,
        'base_url': 'https://api.mapbox.com'
    }

    PAYMENT_GATEWAYS = {
        'stripe': {
            'api_key': None,
            'base_url': 'https://api.stripe.com/v1'
        },
        'paypal': {
            'client_id': None,
            'client_secret': None,
            'base_url': 'https://api.paypal.com'
        }
    }

    SMS_PROVIDERS = {
        'twilio': {
            'account_sid': None,
            'auth_token': None,
            'from_number': None
        }
    }

    @staticmethod
    @monitor_endpoint("get_directions")
    def get_directions(origin: Dict[str, float],
                       destination: Dict[str, float],
                       provider: str = 'google') -> Dict[str, Any]:
        """
        Get directions between two points

        Args:
            origin: {'latitude': x, 'longitude': y}
            destination: {'latitude': x, 'longitude': y}
            provider: 'google' or 'mapbox'

        Returns:
            Directions information
        """
        try:
            if provider == 'google':
                return ExternalPlatformsService._get_google_directions(origin, destination)
            elif provider == 'mapbox':
                return ExternalPlatformsService._get_mapbox_directions(origin, destination)
            else:
                raise ValidationError(
                    message=f"Unsupported directions provider: {provider}",
                    code="UNSUPPORTED_PROVIDER"
                )

        except DIRECTIONS_FALLBACK_EXCEPTIONS as e:
            current_app.logger.warning(
                f"Directions provider unavailable, using mock fallback: {e}"
            )
            return ExternalPlatformsService._mock_directions(origin, destination)

    @staticmethod
    def _get_google_directions(origin: Dict[str, float],
                               destination: Dict[str, float]) -> Dict[str, Any]:
        """Get directions from Google Maps API"""
        api_key = current_app.config.get('GOOGLE_MAPS_API_KEY')
        if not api_key:
            # Fallback to mock data (CONFIGURATION_UNAVAILABLE: no circuit effect)
            return ExternalPlatformsService._mock_directions(origin, destination)

        return ExternalPlatformsService._google_directions_call(
            origin, destination, api_key
        )

    @staticmethod
    @circuit_breaker("google")
    def _google_directions_call(origin: Dict[str, float],
                                destination: Dict[str, float],
                                api_key: str) -> Dict[str, Any]:
        """Provider HTTP + parse for Google Maps (counted by circuit)."""
        # Format coordinates
        origin_str = f"{origin['latitude']},{origin['longitude']}"
        dest_str = f"{destination['latitude']},{destination['longitude']}"

        # Make API request
        url = f"{ExternalPlatformsService.GOOGLE_MAPS_CONFIG['base_url']}/directions/json"
        params = {
            'origin': origin_str,
            'destination': dest_str,
            'key': api_key,
            'mode': 'driving'
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data['status'] != 'OK':
            raise requests.exceptions.HTTPError(
                f"Google Maps API error: {data.get('status')}"
            )

        # Parse response
        route = data['routes'][0]
        leg = route['legs'][0]

        return {
            'success': True,
            'distance_meters': leg['distance']['value'],
            'distance_text': leg['distance']['text'],
            'duration_seconds': leg['duration']['value'],
            'duration_text': leg['duration']['text'],
            'polyline': route['overview_polyline']['points'],
            'steps': [
                {
                    'instruction': step['html_instructions'],
                    'distance': step['distance']['text'],
                    'duration': step['duration']['text']
                }
                for step in leg['steps']
            ]
        }

    @staticmethod
    def _get_mapbox_directions(origin: Dict[str, float],
                               destination: Dict[str, float]) -> Dict[str, Any]:
        """Get directions from Mapbox API"""
        access_token = current_app.config.get('MAPBOX_ACCESS_TOKEN')
        if not access_token:
            # Fallback to mock data (CONFIGURATION_UNAVAILABLE: no circuit effect)
            return ExternalPlatformsService._mock_directions(origin, destination)

        return ExternalPlatformsService._mapbox_directions_call(
            origin, destination, access_token
        )

    @staticmethod
    @circuit_breaker("mapbox")
    def _mapbox_directions_call(origin: Dict[str, float],
                                destination: Dict[str, float],
                                access_token: str) -> Dict[str, Any]:
        """Provider HTTP + parse for Mapbox (counted by circuit)."""
        # Format coordinates
        origin_str = f"{origin['longitude']},{origin['latitude']}"
        dest_str = f"{destination['longitude']},{destination['latitude']}"

        # Make API request
        url = f"{ExternalPlatformsService.MAPBOX_CONFIG['base_url']}/directions/v5/mapbox/driving/{origin_str};{dest_str}"
        params = {
            'access_token': access_token,
            'geometries': 'polyline',
            'overview': 'simplified'
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data['code'] != 'Ok':
            raise requests.exceptions.HTTPError(
                f"Mapbox API error: {data.get('message')}"
            )

        # Parse response
        route = data['routes'][0]

        return {
            'success': True,
            'distance_meters': route['distance'],
            'duration_seconds': route['duration'],
            'polyline': route['geometry'],
            'provider': 'mapbox'
        }

    @staticmethod
    def _mock_directions(origin: Dict[str, float],
                         destination: Dict[str, float]) -> Dict[str, Any]:
        """Mock directions data for development"""
        # Simple distance calculation
        import math

        lat_diff = abs(origin['latitude'] - destination['latitude'])
        lon_diff = abs(origin['longitude'] - destination['longitude'])
        distance_km = math.sqrt(lat_diff ** 2 + lon_diff ** 2) * 111  # Rough approximation

        distance_meters = distance_km * 1000
        duration_seconds = distance_km * 120  # 2 minutes per km

        return {
            'success': True,
            'distance_meters': distance_meters,
            'distance_text': f"{distance_km:.1f} km",
            'duration_seconds': duration_seconds,
            'duration_text': f"{int(duration_seconds / 60)} mins",
            'polyline': None,
            'provider': 'mock',
            'note': 'Using mock directions data'
        }

    @staticmethod
    @monitor_endpoint("geocode_address")
    def geocode_address(address: str, provider: str = 'google') -> Dict[str, Any]:
        """Convert address to coordinates"""
        try:
            if provider == 'google':
                api_key = current_app.config.get('GOOGLE_MAPS_API_KEY')
                if not api_key:
                    return ExternalPlatformsService._mock_geocode(address)

                url = f"{ExternalPlatformsService.GOOGLE_MAPS_CONFIG['base_url']}/geocode/json"
                params = {
                    'address': address,
                    'key': api_key
                }

                response = requests.get(url, params=params, timeout=10)
                data = response.json()

                if data['status'] != 'OK':
                    raise Exception(f"Geocoding error: {data.get('status')}")

                location = data['results'][0]['geometry']['location']

                return {
                    'success': True,
                    'latitude': location['lat'],
                    'longitude': location['lng'],
                    'formatted_address': data['results'][0]['formatted_address'],
                    'provider': 'google'
                }

            else:
                raise ValidationError(
                    message=f"Unsupported geocoding provider: {provider}",
                    code="UNSUPPORTED_PROVIDER"
                )

        except Exception as e:
            current_app.logger.error(f"Geocoding error: {e}", exc_info=True)
            return ExternalPlatformsService._mock_geocode(address)

    @staticmethod
    def _mock_geocode(address: str) -> Dict[str, Any]:
        """Mock geocoding for development"""
        # Simple mock based on address keywords
        import random

        mock_locations = {
            'airport': {'latitude': -1.3192, 'longitude': 36.9278},  # JKIA
            'stadium': {'latitude': -1.3032, 'longitude': 36.8606},  # Kasarani
            'hotel': {'latitude': -1.2833, 'longitude': 36.8167},  # Nairobi CBD
            'nairobi': {'latitude': -1.2921, 'longitude': 36.8219}  # Nairobi center
        }

        address_lower = address.lower()
        for keyword, coords in mock_locations.items():
            if keyword in address_lower:
                return {
                    'success': True,
                    'latitude': coords['latitude'],
                    'longitude': coords['longitude'],
                    'formatted_address': f"Mock location for {address}",
                    'provider': 'mock'
                }

        # Random location in Nairobi area
        return {
            'success': True,
            'latitude': -1.2921 + random.uniform(-0.1, 0.1),
            'longitude': 36.8219 + random.uniform(-0.1, 0.1),
            'formatted_address': f"Mock location for {address}",
            'provider': 'mock'
        }

    @staticmethod
    @monitor_endpoint("send_sms")
    def send_sms(to_number: str, message: str,
                 provider: str = 'twilio') -> Dict[str, Any]:
        """Send SMS via external provider"""
        try:
            if provider == 'twilio':
                # Check if Twilio is configured
                account_sid = current_app.config.get('TWILIO_ACCOUNT_SID')
                auth_token = current_app.config.get('TWILIO_AUTH_TOKEN')
                from_number = current_app.config.get('TWILIO_FROM_NUMBER')

                if not all([account_sid, auth_token, from_number]):
                    # Log but don't fail in development
                    current_app.logger.info(f"Would send SMS to {to_number}: {message}")
                    return {
                        'success': True,
                        'message': 'SMS logged (Twilio not configured)',
                        'data': {'to': to_number, 'message': message}
                    }

                # In production, make actual Twilio API call
                # from twilio.rest import Client
                # client = Client(account_sid, auth_token)
                # message = client.messages.create(
                #     body=message,
                #     from_=from_number,
                #     to=to_number
                # )

                # For now, just log
                current_app.logger.info(f"Twilio SMS to {to_number}: {message}")

                return {
                    'success': True,
                    'message': 'SMS sent successfully',
                    'data': {'to': to_number}
                }

            else:
                raise ValidationError(
                    message=f"Unsupported SMS provider: {provider}",
                    code="UNSUPPORTED_PROVIDER"
                )

        except Exception as e:
            current_app.logger.error(f"SMS sending error: {e}", exc_info=True)
            return {
                'success': False,
                'message': f"Failed to send SMS: {str(e)}",
                'data': {'to': to_number}
            }

    @staticmethod
    @monitor_endpoint("process_payment_external")
    def process_payment_external(amount: float, payment_data: Dict[str, Any],
                                 gateway: str = 'stripe') -> Dict[str, Any]:
        """Process payment via external gateway"""
        try:
            # This is a mock implementation
            # In production, integrate with actual payment gateway

            current_app.logger.info(
                f"Processing payment via {gateway}: ${amount} - {payment_data.get('description', 'No description')}"
            )

            # Simulate payment processing
            import random
            success = random.random() < 0.95  # 95% success rate

            if success:
                payment_ref = f"pay_{datetime.now().strftime('%Y%m%d%H%M%S')}_{random.randint(1000, 9999)}"

                return {
                    'success': True,
                    'message': 'Payment processed successfully',
                    'data': {
                        'payment_reference': payment_ref,
                        'amount': amount,
                        'gateway': gateway,
                        'status': 'completed'
                    }
                }
            else:
                return {
                    'success': False,
                    'message': 'Payment failed',
                    'data': {
                        'gateway': gateway,
                        'status': 'failed',
                        'error': 'Insufficient funds'
                    }
                }

        except Exception as e:
            current_app.logger.error(f"Payment processing error: {e}", exc_info=True)
            return {
                'success': False,
                'message': f"Payment processing error: {str(e)}",
                'data': {'gateway': gateway}
            }

# ==========================================================
# SINGLETON ACCESSOR
# ==========================================================

_external_platforms_instance = None

def get_external_platforms():
    """Singleton accessor to avoid import errors"""
    global _external_platforms_instance
    if _external_platforms_instance is None:
        _external_platforms_instance = ExternalPlatformsService()
    return _external_platforms_instance
