# tests/transport_model.py - UPDATED
from app import create_app

app = create_app()

print("=" * 60)
print("TRANSPORT MODULE VERIFICATION - UPDATED PATH")
print("=" * 60)

with app.app_context():
    try:
        # Test 1: Try importing from the correct path
        print("\n1. Testing model imports from app.transport.models...")
        try:
            from app.transport.models import (
                DriverProfile, OrganisationTransportProfile, Vehicle,
                Booking, BookingPayment, Rating, ScheduledRoute,
                ContingencyPlan, DemandForecast, TransportIncident,
                TransportSetting
            )

            print("✅ All models import successfully from app.transport.models")
        except ImportError as e:
            print(f"❌ Import error from app.transport.models: {e}")

        # Test 2: Alternative import path
        print("\n2. Testing alternative import path...")
        try:
            # Try relative import
            import app.transport.models as transport_models

            print(f"✅ Can import transport.models module: {transport_models}")
        except ImportError as e:
            print(f"❌ Cannot import transport.models: {e}")

        # Test 3: Check what's in app.transport
        print("\n3. Checking app.transport contents...")
        import app.transport

        print(f"✅ app.transport module: {app.transport}")
        print(f"   File: {app.transport.__file__}")

        # List contents
        import inspect

        members = inspect.getmembers(app.transport)
        print(f"   Members: {[name for name, obj in members if not name.startswith('_')]}")

        # Test 4: Database check
        print("\n4. Checking database...")
        from app.extensions import db
        from sqlalchemy import inspect, text

        inspector = inspect(db.engine)
        existing_tables = inspector.get_table_names()
        print(f"✅ Database connected. Total tables: {len(existing_tables)}")

        # Check if transport tables exist
        transport_tables = [
            'driver_profiles',
            'organisation_transport_profiles',
            'transport_vehicles',
            'transport_bookings',
            'transport_booking_payments',
            'transport_ratings',
            'transport_scheduled_routes',
            'transport_contingency_plans',
            'transport_demand_forecasts',
            'transport_incidents',
            'transport_settings',
            'organisation_drivers'
        ]

        print("\nTransport tables status:")
        for table in transport_tables:
            if table in existing_tables:
                print(f"  ⚠️  {table} - ALREADY EXISTS")
            else:
                print(f"  ✅ {table} - Will be created")

        # Test 5: Check SQLAlchemy metadata
        print("\n5. Checking SQLAlchemy metadata...")
        metadata_tables = list(db.metadata.tables.keys())
        print(f"Total tables in metadata: {len(metadata_tables)}")

        # Look for transport tables in metadata
        transport_in_metadata = [t for t in metadata_tables if
                                 any(tl in t for tl in ['driver', 'transport', 'organisation'])]
        print(f"Transport-related tables in metadata: {len(transport_in_metadata)}")

        if transport_in_metadata:
            print("Found in metadata:")
            for table in transport_in_metadata:
                print(f"  - {table}")

        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)

        # Check if we're ready for migration
        transport_tables_in_metadata = all(
            any(tl in table for tl in ['driver', 'transport']) for table in transport_tables[:3])

        if transport_tables_in_metadata:
            print("✅ Ready for migration!")
            print("\nRun these commands:")
            print("1. flask db migrate -m \"Add transport module tables\"")
            print("2. flask db upgrade")
        else:
            print("❌ Transport tables not in metadata")
            print("\nCheck that models are imported in app/transport/__init__.py")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()