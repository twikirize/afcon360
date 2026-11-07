"""Transport pickup timezone adapter backed by shared location timezone rules."""
from app.utils.location_timezone import timezone_for_coordinates


def timezone_for_pickup_coordinates(latitude, longitude) -> str:
    """Resolve a validated pickup point to its IANA timezone, never browser TZ."""
    return timezone_for_coordinates(latitude, longitude)
