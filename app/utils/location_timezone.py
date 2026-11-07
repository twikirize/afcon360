"""Authoritative IANA timezone lookup for physical business locations.

Resolve by explicit IANA selection first, then WGS84 location coordinates, and
only then a country default when that country has one unambiguous zone for the
supported business context. Never use browser, IP or host-system timezone.
"""
from __future__ import annotations

from typing import Optional

from timezonefinder import timezone_at_land

from app.utils.time_policy import require_iana_timezone


_COUNTRY_ALIASES = {
    "UG": "Africa/Kampala", "UGANDA": "Africa/Kampala",
    "KE": "Africa/Nairobi", "KENYA": "Africa/Nairobi",
    "TZ": "Africa/Dar_es_Salaam", "TANZANIA": "Africa/Dar_es_Salaam",
    "RW": "Africa/Kigali", "RWANDA": "Africa/Kigali",
    "BI": "Africa/Bujumbura", "BURUNDI": "Africa/Bujumbura",
    "SS": "Africa/Juba", "SOUTH SUDAN": "Africa/Juba",
    "ET": "Africa/Addis_Ababa", "ETHIOPIA": "Africa/Addis_Ababa",
    "NG": "Africa/Lagos", "NIGERIA": "Africa/Lagos",
    "GH": "Africa/Accra", "GHANA": "Africa/Accra",
    "ZM": "Africa/Lusaka", "ZAMBIA": "Africa/Lusaka",
    "MW": "Africa/Blantyre", "MALAWI": "Africa/Blantyre",
    "MZ": "Africa/Maputo", "MOZAMBIQUE": "Africa/Maputo",
    "ZW": "Africa/Harare", "ZIMBABWE": "Africa/Harare",
    "BW": "Africa/Gaborone", "BOTSWANA": "Africa/Gaborone",
    "NA": "Africa/Windhoek", "NAMIBIA": "Africa/Windhoek",
    "ZA": "Africa/Johannesburg", "SOUTH AFRICA": "Africa/Johannesburg",
    "LS": "Africa/Maseru", "LESOTHO": "Africa/Maseru",
    "SZ": "Africa/Mbabane", "ESWATINI": "Africa/Mbabane",
    "SN": "Africa/Dakar", "SENEGAL": "Africa/Dakar",
    "CI": "Africa/Abidjan", "IVORY COAST": "Africa/Abidjan",
    "COTE D'IVOIRE": "Africa/Abidjan",
    "CM": "Africa/Douala", "CAMEROON": "Africa/Douala",
    "AO": "Africa/Luanda", "ANGOLA": "Africa/Luanda",
    "CD": "Africa/Kinshasa", "DR CONGO": "Africa/Kinshasa",
    "CG": "Africa/Brazzaville", "CONGO": "Africa/Brazzaville",
    "MA": "Africa/Casablanca", "MOROCCO": "Africa/Casablanca",
    "DZ": "Africa/Algiers", "ALGERIA": "Africa/Algiers",
    "TN": "Africa/Tunis", "TUNISIA": "Africa/Tunis",
    "EG": "Africa/Cairo", "EGYPT": "Africa/Cairo",
    "GB": "Europe/London", "UK": "Europe/London",
    "UNITED KINGDOM": "Europe/London",
    "IE": "Europe/Dublin", "IRELAND": "Europe/Dublin",
    "DE": "Europe/Berlin", "GERMANY": "Europe/Berlin",
    "FR": "Europe/Paris", "FRANCE": "Europe/Paris",
    "ES": "Europe/Madrid", "SPAIN": "Europe/Madrid",
    "IT": "Europe/Rome", "ITALY": "Europe/Rome",
    "NL": "Europe/Amsterdam", "NETHERLANDS": "Europe/Amsterdam",
    "BE": "Europe/Brussels", "BELGIUM": "Europe/Brussels",
    "CH": "Europe/Zurich", "SWITZERLAND": "Europe/Zurich",
    "AT": "Europe/Vienna", "AUSTRIA": "Europe/Vienna",
    "PT": "Europe/Lisbon", "PORTUGAL": "Europe/Lisbon",
    "GR": "Europe/Athens", "GREECE": "Europe/Athens",
    "TR": "Europe/Istanbul", "TURKEY": "Europe/Istanbul",
    "AE": "Asia/Dubai", "UNITED ARAB EMIRATES": "Asia/Dubai",
    "SA": "Asia/Riyadh", "SAUDI ARABIA": "Asia/Riyadh",
    "IN": "Asia/Kolkata", "INDIA": "Asia/Kolkata",
    "JP": "Asia/Tokyo", "JAPAN": "Asia/Tokyo",
    "KR": "Asia/Seoul", "SOUTH KOREA": "Asia/Seoul",
    "SG": "Asia/Singapore", "SINGAPORE": "Asia/Singapore",
    "TH": "Asia/Bangkok", "THAILAND": "Asia/Bangkok",
    "VN": "Asia/Ho_Chi_Minh", "VIETNAM": "Asia/Ho_Chi_Minh",
    "PH": "Asia/Manila", "PHILIPPINES": "Asia/Manila",
    "ID": "Asia/Jakarta", "INDONESIA": "Asia/Jakarta",
    "AU": None, "AUSTRALIA": None,
    "US": None, "USA": None, "UNITED STATES": None,
    "CA": None, "CANADA": None,
    "MX": None, "MEXICO": None,
    "BR": None, "BRAZIL": None,
    "RU": None, "RUSSIA": None,
}


def timezone_for_country(country: Optional[str]) -> Optional[str]:
    """Return a country default only where one zone is a reasonable default.

    Multi-timezone countries intentionally return None and require coordinates
    or an explicit venue/property IANA zone.
    """
    token = str(country or "").strip().upper()
    if not token:
        return None
    if token in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[token]
    return None


def timezone_for_coordinates(latitude, longitude) -> str:
    """Resolve a WGS84 land point to its IANA timezone; reject unresolved points."""
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError) as exc:
        raise ValueError("Latitude and longitude are required to resolve a location timezone") from exc
    timezone_name = timezone_at_land(lng=lng, lat=lat)
    if not timezone_name:
        raise ValueError(
            "Location coordinates have no resolvable land timezone; "
            "provide an explicit IANA timezone"
        )
    return require_iana_timezone(
        timezone_name, field="location timezone"
    ).key


def resolve_location_timezone(
    *,
    explicit_timezone: Optional[str] = None,
    latitude=None,
    longitude=None,
    country: Optional[str] = None,
) -> str:
    """Resolve explicit IANA zone -> coordinates -> unambiguous country default."""
    if explicit_timezone is not None and str(explicit_timezone).strip():
        return require_iana_timezone(
            str(explicit_timezone).strip(), field="location timezone"
        ).key
    has_lat = latitude is not None and str(latitude).strip() != ""
    has_lon = longitude is not None and str(longitude).strip() != ""
    if has_lat != has_lon:
        raise ValueError("Both latitude and longitude are required to resolve a location timezone")
    if has_lat:
        return timezone_for_coordinates(latitude, longitude)
    country_zone = timezone_for_country(country)
    if country_zone:
        return require_iana_timezone(country_zone, field="country default timezone").key
    raise ValueError(
        "A venue/property timezone is required for this location. "
        "Enter an IANA timezone such as Africa/Kampala or provide precise coordinates."
    )



def timezone_for_property(property_obj, *, explicit_timezone=None, country=None):
    """Resolve a property's business timezone without using ambient machine state."""
    return resolve_location_timezone(
        explicit_timezone=(
            explicit_timezone
            if explicit_timezone is not None
            else getattr(property_obj, "timezone_name", None)
        ),
        latitude=getattr(property_obj, "latitude", None),
        longitude=getattr(property_obj, "longitude", None),
        country=country if country is not None else getattr(property_obj, "country", None),
    )
