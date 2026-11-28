"""Test helpers for issuing deterministic, signed road-distance quotes.

Production never trusts test/client-supplied route measurements. These helpers
create the same signed v2 token the real ride-options endpoint issues, using
fixed GEO measurements so booking-service tests do not depend on live routing.
"""
from datetime import datetime
from decimal import Decimal


TEST_ROUTE_DISTANCE_KM = 8.75
TEST_ROUTE_DURATION_S = 1260.0
TEST_ROUTE_PROVIDER = "test-routing-provider"


def add_test_road_quote(payload, *, distance_km=TEST_ROUTE_DISTANCE_KM,
                        duration_s=TEST_ROUTE_DURATION_S,
                        provider=TEST_ROUTE_PROVIDER):
    """Mutate and return a BookingService payload with a valid road quote."""
    from app.transport.services.fare_service import calculate_estimate
    from app.transport.services.fare_quote_service import (
        issue_fare_quote,
        money_amount,
    )

    pickup = {
        "latitude": payload.get("pickup_latitude"),
        "longitude": payload.get("pickup_longitude"),
    }
    dropoff = {
        "latitude": payload.get("dropoff_latitude"),
        "longitude": payload.get("dropoff_longitude"),
    }
    if pickup["latitude"] is None and isinstance(payload.get("pickup_location"), dict):
        pickup = payload["pickup_location"]
    if dropoff["latitude"] is None and isinstance(payload.get("dropoff_location"), dict):
        dropoff = payload["dropoff_location"]

    quoted_at = datetime.now().replace(microsecond=0)
    estimate = calculate_estimate(
        service_type=payload.get("service_type") or "on_demand",
        vehicle_class=payload.get("vehicle_class") or "comfort",
        distance_km=distance_km,
        at=quoted_at,
    )
    currency = str(estimate.get("currency") or "USD").upper()
    amount = money_amount(estimate["total"])
    payload["currency"] = currency
    payload["confirmed_fare_amount"] = format(amount, ".2f")
    payload["fare_quote_token"] = issue_fare_quote(
        service_type=payload.get("service_type") or "on_demand",
        vehicle_class=payload.get("vehicle_class") or "comfort",
        currency=currency,
        amount=amount,
        fare_version=estimate.get("version"),
        pickup=pickup,
        dropoff=dropoff,
        distance_km=distance_km,
        route_duration_s=duration_s,
        route_provider=provider,
        quoted_at=quoted_at,
    )
    return payload


def add_test_ride_request_quote(payload, *, distance_km=TEST_ROUTE_DISTANCE_KM,
                                duration_s=TEST_ROUTE_DURATION_S,
                                provider=TEST_ROUTE_PROVIDER):
    """Add a v2 quote to a request-first payload with nested endpoints."""
    from app.transport.services.fare_service import calculate_estimate
    from app.transport.services.fare_quote_service import (
        issue_fare_quote,
        money_amount,
    )

    quoted_at = datetime.now().replace(microsecond=0)
    estimate = calculate_estimate(
        service_type=payload.get("service_type") or "on_demand",
        vehicle_class=payload.get("vehicle_class") or "comfort",
        distance_km=distance_km,
        at=quoted_at,
    )
    currency = str(estimate.get("currency") or "USD").upper()
    amount = money_amount(estimate["total"])
    payload["currency"] = currency
    payload["confirmed_fare_amount"] = format(Decimal(str(amount)), ".2f")
    payload["fare_quote_token"] = issue_fare_quote(
        service_type=payload.get("service_type") or "on_demand",
        vehicle_class=payload.get("vehicle_class") or "comfort",
        currency=currency,
        amount=amount,
        fare_version=estimate.get("version"),
        pickup=payload["pickup"],
        dropoff=payload["dropoff"],
        distance_km=distance_km,
        route_duration_s=duration_s,
        route_provider=provider,
        quoted_at=quoted_at,
    )
    return payload
