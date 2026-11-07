"""Server-side IANA timezone resolution for transport pickup coordinates."""
from functools import lru_cache

from timezonefinder import TimezoneFinder

from app.utils.time_policy import require_iana_timezone


@lru_cache(maxsize=1)
def _finder():
    # Reuse the packaged offline boundary index for the life of this worker.
    return TimezoneFinder(in_memory=False)


def timezone_for_pickup_coordinates(latitude, longitude) -> str:
    """Resolve a land pickup point to an IANA timezone; never trust browser TZ."""
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError) as exc:
        raise ValueError("Pickup coordinates are required to resolve local time") from exc
    timezone_name = _finder().timezone_at_land(lng=lng, lat=lat)
    if not timezone_name:
        raise ValueError(
            "The pickup point has no resolvable land timezone; select a pickup point on land"
        )
    return require_iana_timezone(
        timezone_name, field="pickup location timezone"
    ).key
