# check_models_status.py
from app import create_app

app = create_app()

print("=" * 60)
print("CHECKING TRANSPORT MODELS STATUS")
print("=" * 60)

with app.app_context():
    # Check imports
    print("\n🔍 Checking imports in models.py...")
    try:
        import app.transport.models as transport_models

        # Check for geoalchemy2 import
        source = open('app/transport/models.py', 'r').read()

        if 'from geoalchemy2 import Geometry' in source:
            print("❌ geoalchemy2 import STILL PRESENT (should be commented out)")
        else:
            print("✅ geoalchemy2 import removed/commented out")

        if 'JSONB' in source:
            print("✅ JSONB import present")
        else:
            print("⚠️  JSONB import might be missing")

    except Exception as e:
        print(f"❌ Error checking imports: {e}")

    # Check column types
    print("\n🔍 Checking column types in actual tables...")
    from app.extensions import db
    from sqlalchemy import inspect

    inspector = inspect(db.engine)

    # Check specific columns that should be JSONB, not geometry
    tables_to_check = {
        'transport_vehicles': 'current_location',
        'transport_bookings': ['pickup_point', 'dropoff_point'],
        'transport_scheduled_routes': 'path_coordinates'
    }

    for table, columns in tables_to_check.items():
        if isinstance(columns, str):
            columns = [columns]

        for column in columns:
            try:
                col_info = inspector.get_columns(table)
                for col in col_info:
                    if col['name'] == column:
                        col_type = str(col['type'])
                        if 'JSON' in col_type.upper() or 'JSONB' in col_type.upper():
                            print(f"✅ {table}.{column}: {col_type} (Correct - JSONB)")
                        elif 'GEOMETRY' in col_type.upper():
                            print(f"❌ {table}.{column}: {col_type} (WRONG - should be JSONB)")
                        else:
                            print(f"⚠️  {table}.{column}: {col_type} (Unknown type)")
            except Exception as e:
                print(f"❌ Could not check {table}.{column}: {e}")

    # Test model instantiation
    print("\n🧪 Testing model instantiation...")
    try:
        from app.transport.models import DriverProfile, Vehicle, Booking

        # Test creating objects
        driver = DriverProfile(
            user_id=1000001,
            driver_code="CHECK-001",
            verification_tier="PENDING",
            reliability_score=80,
            safety_score=80
        )

        vehicle = Vehicle(
            owner_type='driver',
            owner_id=1000001,
            license_plate='CHECK-001',
            make='Test',
            model='Model',
            year=2023,
            vehicle_type='Sedan',
            vehicle_class='comfort',
            passenger_capacity=4,
            current_location={'lat': 1.23, 'lng': 4.56}  # Should work with JSONB
        )

        booking = Booking(
            user_id=2000001,
            provider_type='individual_driver',
            service_type='on_demand',
            pickup_location={'lat': 1.23, 'lng': 4.56},
            dropoff_location={'lat': 2.34, 'lng': 5.67},
            pickup_time='2024-02-10 10:00:00',
            passenger_count=2,
            base_price=100.00,
            subtotal=100.00,
            total_amount=100.00,
            final_price=100.00,
            currency='USD',
            status='confirmed',
            pickup_point={'lat': 1.23, 'lng': 4.56},  # Should work with JSONB
            dropoff_point={'lat': 2.34, 'lng': 5.67}  # Should work with JSONB
        )

        print("✅ Models can be instantiated with JSONB location data")

    except Exception as e:
        print(f"❌ Model instantiation failed: {e}")
        import traceback

        traceback.print_exc()

    print("\n" + "=" * 60)
    print("RECOMMENDATION:")
    print("=" * 60)
    print("1. Check app/transport/models.py manually")
    print("2. Make sure Geometry columns are changed to JSONB")
    print("3. Make sure geoalchemy2 import is commented out")
    print("4. Make sure JSONB is imported from sqlalchemy.dialects.postgresql")
