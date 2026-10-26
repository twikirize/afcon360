# app/schemas/transport.py
#
# Rules mirrored from (nothing added):
#   app/utils/validators.py::TransportValidators.validate_booking_request
#   app/transport/services/booking_service.py::create_booking (defaults, enums)
#   app/transport/services/booking_service.py::_extract_coords
#   app/transport/services/booking_service.py::_validate_booking_location_coordinates
#
# STRING PRESERVATION: every field returns the original string. The service
# re-parses (ServiceType(v.lower()), int(v), float(v), datetime.fromisoformat(v)).
# Coercing here would break those calls.
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .common import BaseSchema

# Enum value sets (mirror app/transport/models.py)
_SERVICE_TYPES = {
    "airport_arrival", "airport_departure", "stadium_shuttle", "hotel_transfer",
    "city_tour", "on_demand", "scheduled_route", "custom_tour",
}
_PROVIDER_TYPES = {
    "individual_driver", "hotel_fleet", "tour_operator",
    "transport_company", "external_platform",
}
_VEHICLE_CLASSES = {"economy", "comfort", "premium", "luxury", "van", "bus"}
_CURRENCIES = {"USD", "EUR", "GBP", "XOF", "XAF", "NGN", "KES", "GHS", "ZAR", "UGX"}
# Canonical contract: app/transport/services/location_snapshot.py::VALID_SOURCES.
# Kept as a local literal rather than importing the transport service (that
# import drags in the whole `app.transport.services` package). Equality with
# the canonical set is pinned by
# tests/transport/test_booking_schema_shadow.py::test_source_keys_match_canonical.
_SOURCE_KEYS = {"gps", "map", "search", "curated"}


def _int_in_range(v: str, lo: int, hi: int) -> str:
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ValueError("must be an integer")
    if n < lo or n > hi:
        raise ValueError(f"must be between {lo} and {hi}")
    return v  # original string preserved


def _float_coord(v: str, kind: str) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ValueError("must be numeric")
    # bool-safe: 'true'/'false' would fail float() above
    if kind == "lat" and not (-90.0 <= f <= 90.0):
        raise ValueError("latitude must be between -90 and 90")
    if kind == "lng" and not (-180.0 <= f <= 180.0):
        raise ValueError("longitude must be between -180 and 180")
    return v


def _is_iso8601(v: str) -> bool:
    from datetime import datetime
    try:
        datetime.fromisoformat(str(v))
        return True
    except (TypeError, ValueError):
        return False


class _BookingModel(BaseModel):
    # Mirrors Marshmallow's Meta.unknown = "exclude"
    model_config = ConfigDict(extra="ignore")

    # Required (validators.py:283-362)
    pickup_location: str = Field(min_length=1)
    dropoff_location: str = Field(min_length=1)
    # Optional at the boundary: instant rides carry no client pickup_time
    # (create_booking stamps the server clock); scheduled rides require
    # an explicit ISO time — enforced by the service, mirrored here.
    pickup_time: Optional[str] = None
    service_type: str

    # Optional with service defaults (create_booking)
    provider_type: str = "individual_driver"
    passenger_count: str = "1"
    luggage_count: str = "0"
    payment_method: str = "cash"
    currency: str = "USD"
    vehicle_class: Optional[str] = None
    preferred_vehicle_class: Optional[str] = None

    # Coordinates (optional; both-or-neither enforced in model_validator)
    pickup_latitude: Optional[str] = None
    pickup_longitude: Optional[str] = None
    dropoff_latitude: Optional[str] = None
    dropoff_longitude: Optional[str] = None

    # Method-integrity markers (optional; service validates if non-empty)
    pickup_source: Optional[str] = None
    dropoff_source: Optional[str] = None
    pickup_geocode: Optional[str] = None
    dropoff_geocode: Optional[str] = None

    pickup_address: Optional[str] = None
    dropoff_address: Optional[str] = None
    special_requirements: Optional[str] = None
    accessibility_requirements: Optional[str] = None
    estimated_duration: Optional[str] = None
    scheduled_time: Optional[str] = None
    idempotency_key: Optional[str] = None

    # --- Validators (mirror the service; add nothing) ---

    @field_validator("service_type")
    @classmethod
    def _check_service(cls, v: str) -> str:
        if v.lower() not in _SERVICE_TYPES:
            raise ValueError(f"service_type must be one of {sorted(_SERVICE_TYPES)}")
        return v

    @field_validator("provider_type")
    @classmethod
    def _check_provider(cls, v: str) -> str:
        if v.lower() not in _PROVIDER_TYPES:
            raise ValueError(f"provider_type must be one of {sorted(_PROVIDER_TYPES)}")
        return v

    @field_validator("currency")
    @classmethod
    def _check_currency(cls, v: str) -> str:
        if v not in _CURRENCIES:
            raise ValueError(f"currency must be one of {sorted(_CURRENCIES)}")
        return v

    @field_validator("vehicle_class", "preferred_vehicle_class")
    @classmethod
    def _check_vehicle(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return v
        if v.lower() not in _VEHICLE_CLASSES:
            raise ValueError(f"vehicle_class must be one of {sorted(_VEHICLE_CLASSES)}")
        return v

    @field_validator("pickup_time")
    @classmethod
    def _check_pickup_time(cls, v: Optional[str]) -> Optional[str]:
        if v is None or str(v).strip() == "":
            return v
        if not _is_iso8601(v):
            raise ValueError("pickup_time must be ISO-8601")
        return v

    @field_validator("passenger_count")
    @classmethod
    def _check_passengers(cls, v: str) -> str:
        return _int_in_range(v, 1, 100)

    @field_validator("luggage_count")
    @classmethod
    def _check_luggage(cls, v: str) -> str:
        return _int_in_range(v, 0, 1000)

    @field_validator("pickup_latitude")
    @classmethod
    def _check_p_lat(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return _float_coord(v, "lat")

    @field_validator("pickup_longitude")
    @classmethod
    def _check_p_lng(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return _float_coord(v, "lng")

    @field_validator("dropoff_latitude")
    @classmethod
    def _check_d_lat(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return _float_coord(v, "lat")

    @field_validator("dropoff_longitude")
    @classmethod
    def _check_d_lng(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return _float_coord(v, "lng")

    @field_validator("pickup_source", "dropoff_source")
    @classmethod
    def _check_source(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if v not in _SOURCE_KEYS:
            raise ValueError(f"source must be one of {sorted(_SOURCE_KEYS)}")
        return v

    @model_validator(mode="after")
    def _pair_coordinates_and_geocode(self):
        # Both-or-neither for each side (mirrors _extract_coords + _validate_*)
        if (self.pickup_latitude is None) != (self.pickup_longitude is None):
            raise ValueError("pickup_location must include both 'latitude' and 'longitude'")
        if (self.dropoff_latitude is None) != (self.dropoff_longitude is None):
            raise ValueError("dropoff_location must include both 'latitude' and 'longitude'")

        # search source requires geocode evidence (mirrors _search_geocode_result)
        if self.pickup_source == "search" and not (self.pickup_geocode or "").strip():
            raise ValueError("pickup_source 'search' requires pickup_geocode evidence")
        if self.dropoff_source == "search" and not (self.dropoff_geocode or "").strip():
            raise ValueError("dropoff_source 'search' requires dropoff_geocode evidence")

        # special_requirements length cap (validators.py)
        if self.special_requirements and len(self.special_requirements) > 500:
            raise ValueError("special_requirements must be 500 characters or fewer")

        return self


class BookingSchema(BaseSchema):
    """Rider booking form. Mirrors the service rules exactly; adds nothing."""
    Model = _BookingModel


__all__ = ["BookingSchema"]
