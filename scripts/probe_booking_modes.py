import sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, ".")

from app import create_app
from app.transport.services.booking_service import get_booking_service
from app.utils.exceptions import ValidationError
from app.transport.models import Booking
from app.extensions import db

app = create_app()
TEST_USER_ID = 1
TEST_REFERENCES = []
results = []

def try_booking(label, payload):
    try:
        r = get_booking_service().create_booking(TEST_USER_ID, payload)
        ref = r["data"]["booking_reference"]
        TEST_REFERENCES.append(ref)
        results.append((label, "SUCCESS", ref))
    except ValidationError as e:
        results.append((label, "ValidationError", str(e.message)[:120]))
    except Exception as e:
        results.append((label, type(e).__name__, str(e)[:120]))

def base_payload(mode, pickup_time):
    payload = {
        "service_type": "on_demand",
        "provider_type": "individual_driver",
        "pickup_latitude":  0.3136,
        "pickup_longitude": 32.5811,
        "dropoff_latitude":  0.3476,
        "dropoff_longitude": 32.5825,
        "pickup_location":  "Kampala",
        "dropoff_location": "Entebbe",
        "pickup_time": pickup_time.isoformat(),
        "passenger_count": 1,
        "currency": "USD",
        "payment_method": "cash",
        "vehicle_class": "comfort",
        "booking_mode": mode,
    }
    from app.transport.services.road_distance_service import measure_road_route
    from app.transport.services.fare_service import calculate_estimate
    from app.transport.services.fare_quote_service import issue_fare_quote, money_amount

    pickup = {"latitude": payload["pickup_latitude"], "longitude": payload["pickup_longitude"]}
    dropoff = {"latitude": payload["dropoff_latitude"], "longitude": payload["dropoff_longitude"]}
    route = measure_road_route(pickup, dropoff)
    quoted_at = datetime.now().replace(microsecond=0)
    estimate = calculate_estimate(
        service_type=payload["service_type"],
        vehicle_class=payload["vehicle_class"],
        distance_km=route["distance_km"],
        at=quoted_at,
    )
    amount = money_amount(estimate["total"])
    payload["currency"] = str(estimate.get("currency") or "USD").upper()
    payload["confirmed_fare_amount"] = format(amount, ".2f")
    payload["fare_quote_token"] = issue_fare_quote(
        service_type=payload["service_type"],
        vehicle_class=payload["vehicle_class"],
        currency=payload["currency"],
        amount=amount,
        fare_version=estimate.get("version"),
        pickup=pickup,
        dropoff=dropoff,
        distance_km=route["distance_km"],
        route_duration_s=route["duration_s"],
        route_provider=route["provider"],
        quoted_at=quoted_at,
    )
    return payload


with app.app_context():
    now = datetime.now(timezone.utc)

    try_booking("instant + now", base_payload("instant", now))
    try_booking("scheduled + 30min", base_payload("scheduled", now + timedelta(minutes=30)))
    try_booking("scheduled + 3min (should fail)", base_payload("scheduled", now + timedelta(minutes=3)))
    naive = (now + timedelta(minutes=20)).replace(tzinfo=None)
    try_booking("scheduled + 20min naive", base_payload("scheduled", naive))

    print()
    print(f"{'CASE':<35} {'RESULT':<18} {'DETAIL'}")
    print("-" * 90)
    for label, result, detail in results:
        print(f"{label:<35} {result:<18} {detail}")

    print()
    print(f"Cleaning up {len(TEST_REFERENCES)} test bookings...")
    for ref in TEST_REFERENCES:
        b = Booking.query.filter_by(booking_reference=ref).first()
        if b:
            db.session.delete(b)
    db.session.commit()
    print("Done. DB is clean.")
