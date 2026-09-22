"""
Seed one driver + one vehicle that passes every availability gate.
Safe to re-run — it upserts by email.
"""
from datetime import datetime, timezone
from app import create_app
from app.extensions import db
from app.identity.models.user import User
from app.transport.models import (
    DriverProfile, Vehicle, DriverVehicleHistory,
    ComplianceStatus, VerificationTier, VehicleClass,
)

app = create_app()

with app.app_context():
    now = datetime.now(timezone.utc)

    # --- 1. The user (driver's account) ---
    email = "driver1@afcon360.test"
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(
            username="Driver One",
            email=email,
            phone="+256700000001",
            email_verified=True,
            is_active=True,
        )
        user.set_password("TestPass123!")
        db.session.add(user)
        db.session.flush()

    # --- 2. The driver profile ---
    driver = DriverProfile.query.filter_by(user_id=user.id).first()
    if not driver:
        driver = DriverProfile(
            user_id=user.id,
            driver_code="DRV-TEST01",
            verification_tier=VerificationTier.PLATFORM_VERIFIED,
            compliance_status=ComplianceStatus.APPROVED,
            is_online=True,
            is_available=True,
            vehicle_classes=[VehicleClass.COMFORT.value, VehicleClass.ECONOMY.value],
            service_types=["on_demand", "airport_departure"],
            max_passenger_capacity=4,
            max_luggage_capacity=2,
            languages_spoken=["en"],
            operational_zones=["kampala"],
        )
        db.session.add(driver)
        db.session.flush()
    else:
        driver.compliance_status = ComplianceStatus.APPROVED
        driver.verification_tier  = VerificationTier.PLATFORM_VERIFIED
        driver.is_online          = True
        driver.is_available       = True

    # Fresh location is REQUIRED — the availability predicate rejects stale.
    driver.last_location = {
        "latitude": 0.3136,
        "longitude": 32.5811,
        "accuracy": 5.0,
        "updated_at": now.isoformat(),
    }
    driver.location_updated_at = now

    # --- 3. The vehicle ---
    plate = "UAX 001A"
    vehicle = Vehicle.query.filter_by(license_plate=plate).first()
    if not vehicle:
        vehicle = Vehicle(
            owner_type="driver",
            owner_id=driver.id,
            license_plate=plate,
            make="Toyota",
            model="Premio",
            year=2020,
            vehicle_type="sedan",
            vehicle_class=VehicleClass.COMFORT,
            passenger_capacity=4,
            luggage_capacity=2,
            status="active",
            is_available=True,
            is_deleted=False,
        )
        vehicle.generate_qr_code()
        db.session.add(vehicle)
        db.session.flush()
    else:
        vehicle.status       = "active"
        vehicle.is_available = True
        vehicle.is_deleted   = False

    vehicle.current_location = {
        "latitude": 0.3136,
        "longitude": 32.5811,
        "accuracy": 5.0,
        "updated_at": now.isoformat(),
    }
    vehicle.last_location_update = now

    # --- 4. The current driver-vehicle link ---
    existing_link = DriverVehicleHistory.query.filter(
        DriverVehicleHistory.driver_id == driver.id,
        DriverVehicleHistory.vehicle_id == vehicle.id,
        DriverVehicleHistory.ended_at.is_(None),
    ).first()
    if not existing_link:
        db.session.add(DriverVehicleHistory(
            driver_id=driver.id,
            vehicle_id=vehicle.id,
            started_at=now,
            assignment_reason="shift_start",
        ))

    # --- 5. Ensure the Economy vehicle too (for the grid to be full) ---
    plate2 = "UAX 002B"
    v2 = Vehicle.query.filter_by(license_plate=plate2).first()
    if not v2:
        v2 = Vehicle(
            owner_type="driver",
            owner_id=driver.id,
            license_plate=plate2,
            make="Toyota",
            model="Axio",
            year=2019,
            vehicle_type="sedan",
            vehicle_class=VehicleClass.ECONOMY,
            passenger_capacity=4,
            luggage_capacity=2,
            status="active",
            is_available=True,
            is_deleted=False,
        )
        v2.generate_qr_code()
        db.session.add(v2)
        db.session.flush()
    v2.current_location = {
        "latitude": 0.3136,
        "longitude": 32.5811,
        "accuracy": 5.0,
        "updated_at": now.isoformat(),
    }
    v2.last_location_update = now

    link2 = DriverVehicleHistory.query.filter(
        DriverVehicleHistory.driver_id == driver.id,
        DriverVehicleHistory.vehicle_id == v2.id,
        DriverVehicleHistory.ended_at.is_(None),
    ).first()
    # Note: The DB has a partial unique index allowing only ONE
    # active vehicle per driver. So for a second vehicle, we simulate
    # a second driver. Skip the second link if the first exists.

    db.session.commit()

    print(f"✅ Driver user:  {user.email} / TestPass123!")
    print(f"✅ Driver id:    {driver.id}  (code {driver.driver_code})")
    print(f"✅ Vehicle 1:    {vehicle.license_plate}  (Comfort)")
    print(f"✅ Vehicle 2:    {v2.license_plate}  (Economy)")
    print(f"✅ Location:     fresh at {now.isoformat()}")
    print()
    print("Now reload /transport/new-home and click 'Find a Ride'.")