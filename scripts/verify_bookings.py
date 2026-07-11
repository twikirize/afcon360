from app.cli import create_app
from app.extensions import db
from app.accommodation.services.booking_service import BookingService
from app.accommodation.models.property import Property, RoomType
from app.identity.models.user import User
from datetime import date, timedelta
import uuid
import sys

app = create_app()
with app.app_context():
    # 1. Ensure an Org-owned property with 1 single unit RoomType exists
    org_prop = Property.query.filter(Property.owner_org_id.isnot(None), Property.status == 'ACTIVE').first()
    guest = User.query.first()
    
    if not org_prop:
        print("No active org property found. Creating one for the test...")
        # create one
        org_prop = Property(
            owner_org_id=1, 
            title="Test Org Property", 
            property_type="hotel_room", 
            status="ACTIVE",
            max_guests=2,
            base_price_per_night=100.0,
            currency="USD",
            min_stay_nights=1
        )
        db.session.add(org_prop)
        db.session.flush()
        
        # create a room type for it
        rt = RoomType(
            property_id=org_prop.id,
            name="Org Room",
            max_guests=2,
            base_price_per_night=100.0,
            total_units=1,
            is_active=True
        )
        db.session.add(rt)
        db.session.commit()
        print("Created Org Prop ID:", org_prop.id)
    else:
        # Check if it has a room type, if not add one
        rt = RoomType.query.filter_by(property_id=org_prop.id).first()
        if not rt:
            rt = RoomType(
                property_id=org_prop.id,
                name="Org Room",
                max_guests=2,
                base_price_per_night=100.0,
                total_units=1,
                is_active=True
            )
            db.session.add(rt)
            db.session.commit()

    today = date.today() + timedelta(days=60)
    tomorrow = today + timedelta(days=1)
    
    print('Testing Org Prop:', org_prop)
    try:
        b2, e2 = BookingService.create_booking(
            property_id=org_prop.id,
            guest_user_id=guest.id,
            host_user_id=org_prop.owner_org_id,
            check_in=today,
            check_out=tomorrow,
            num_guests=1,
            guest_name='Test Org',
            guest_email='test2@test.com',
            idempotency_key=str(uuid.uuid4())
        )
        print('Booking 2:', b2, e2)
        if b2: print('Booking 2 room_type_id:', b2.room_type_id)
    except Exception as e:
        print("Error creating b2", e)

    db.session.commit()
    
    res = db.session.execute(db.text("SELECT id, property_id, room_type_id, guest_user_id, status FROM accommodation_bookings WHERE property_id = :pid ORDER BY id DESC LIMIT 5;"), {'pid': org_prop.id})
    print("--- RAW QUERY RESULTS BOOKINGS ---")
    print("id | property_id | room_type_id | guest_user_id | status")
    for row in res:
        print(row)
