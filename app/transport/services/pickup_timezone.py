"""Server-side IANA timezone resolution for transport pickup coordinates."""
from timezonefinder import timezone_at_land

from app.utils.time_policy import require_iana_timezone


def timezone_for_pickup_coordinates(latitude, longitude) -> str:
    """Resolve a land pickup point to an IANA timezone; never trust browser TZ."""
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError) as exc:
        raise ValueError("Pickup coordinates are required to resolve local time") from exc
    timezone_name = timezone_at_land(lng=lng, lat=lat)
    if not timezone_name:
        raise ValueError(
            "The pickup point has no resolvable land timezone; select a pickup point on land"
        )
    return require_iana_timezone(
        timezone_name, field="pickup location timezone"
    ).key
