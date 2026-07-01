#!/usr/bin/env python
"""Run backfill from Flask context."""
import sys
sys.path.insert(0, '.')

from app import create_app
from app.extensions import db
from app.accommodation.models.property import Property, RoomType

app = create_app()

with app.app_context():
    # Find properties that don't have room types yet
    properties_without_room_types = db.session.query(Property).outerjoin(
        RoomType, Property.id == RoomType.property_id
    ).filter(RoomType.id == None).all()
    
    count = 0
    for prop in properties_without_room_types:
        room_type = RoomType(
            property_id=prop.id,
            name="Standard Room",
            description="Default room type for this property",
            max_guests=prop.max_guests,
            bedrooms=prop.bedrooms,
            beds=prop.beds,
            bathrooms=prop.bathrooms,
            base_price_per_night=prop.base_price_per_night,
            currency=prop.currency,
            cleaning_fee=prop.cleaning_fee,
            service_fee_pct=prop.service_fee_pct,
            total_units=1,
            is_active=True,
        )
        db.session.add(room_type)
        count += 1
    
    db.session.commit()
    print(f"Created {count} RoomType records for existing properties.")