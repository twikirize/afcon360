"""Create Kampala Central Hotel via the sanctioned host + moderation lifecycle.

Why this path:
- HostService.create_property() generates the exact slug 'kampala-central-hotel'
  via ensure_unique_slug(slugify(title)) - matching the 404 URL.
- ModerationService.approve_property() + publish_property() move the property
  through the approved/publication lifecycle so it passes the guest-facing
  is_publicly_viewable() gate (active/published + verified + active +
  publicly visible + >=1 active room type).

No migrations are involved; this is data provisioning.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from decimal import Decimal

from app import create_app
from app.extensions import db
from app.accommodation.services.host_service import HostService
from app.accommodation.services.moderation_service import ModerationService
from app.accommodation.models.property import Property
from app.accommodation.models.room import RoomType

TITLE = "Kampala Central Hotel"
SLUG = "kampala-central-hotel"


def main():
    app = create_app()
    with app.app_context():
        owner_user_id = 1  # OBED - platform owner in afcon360_prod
        moderator_id = 1

        existing = Property.query.filter_by(slug=SLUG).first()
        if existing is not None:
            print(f"Property '{SLUG}' already exists (id={existing.id}, status={existing.status})")
            prop = existing
            if prop.is_publicly_viewable():
                print(f"Already publicly viewable: {prop.public_id}")
                print(f"URL: /accommodation/guest/{prop.slug}")
                return
            print("Not yet publicly viewable - attempting to publish via moderation lifecycle")
        else:
            data = {
                "title": TITLE,
                "summary": "Centrally located hotel steps from the stadium and city centre.",
                "description": ("Kampala Central Hotel offers comfortable, modern rooms in the "
                                "heart of the city. Perfect for fans and travellers, with "
                                "convenient access to the stadium, restaurants and transport."),
                "property_type": "hotel",
                "listing_type": "entire_place",
                "address_line1": "123 Main Street",
                "city": "Kampala",
                "country": "UG",
                "postal_code": None,
                "max_guests": 2,
                "bedrooms": 1,
                "beds": 1,
                "bathrooms": 1,
                "base_price_per_night": Decimal("80.00"),
                "currency": "USD",
                "cleaning_fee": Decimal("10.00"),
                "service_fee_pct": Decimal("10.00"),
                "min_stay_nights": 1,
                "max_stay_nights": None,
                "cancellation_policy": "moderate",
                "check_in_time": "14:00",
                "check_out_time": "11:00",
                "instant_book": True,
                "booking_mode": "instant",
                "allow_pets": False,
                "allow_smoking": False,
                "allow_events": False,
                "main_image": ("https://images.unsplash.com/photo-1566073771259-6a8506099945"
                               "?w=1200&q=80"),
                "gallery_urls": None,
            }
            prop = HostService.create_property(data, owner_user_id=owner_user_id, owner_org_id=None)
            db.session.flush()
            print(f"Created property id={prop.id} slug={prop.slug} status={prop.status}")

        # Ensure at least one active sellable room type exists (readiness +
        # public visibility require >=1 active room type with valid config).
        active_room_types = [rt for rt in prop.room_types if rt.is_active]
        if not active_room_types:
            rt = RoomType(
                property_id=prop.id,
                name="Standard Room",
                description="Comfortable standard room with en-suite bathroom.",
                max_guests=2,
                bedrooms=1,
                beds=1,
                bathrooms=1.0,
                base_price_per_night=Decimal("80.00"),
                currency="USD",
                cleaning_fee=Decimal("10.00"),
                service_fee_pct=Decimal("10.00"),
                total_units=5,
                is_active=True,
            )
            db.session.add(rt)
            db.session.flush()
            print(f"Added active room type id={rt.id}")

        # Walk the approved lifecycle.
        if prop.status in ("pending_review", "under_review", "submitted"):
            ok, err = ModerationService.approve_property(prop.id, moderator_id,
                                                         notes="Data provisioning fix for 404 guest page")
            print(f"approve_property -> ok={ok}, err={err}")
            if not ok:
                db.session.rollback()
                raise SystemExit(f"approve failed: {err}")

        if prop.status == "approved":
            ok, err = ModerationService.publish_property(prop.id, moderator_id,
                                                         notes="Data provisioning fix for 404 guest page")
            print(f"publish_property -> ok={ok}, err={err}")
            if not ok:
                db.session.rollback()
                raise SystemExit(f"publish failed: {err}")

        db.session.refresh(prop)
        print(f"Final state: id={prop.id}, slug={prop.slug}, status={prop.status}, "
              f"verified={prop.is_verified}, active={prop.is_active}, "
              f"publicly_visible={prop.is_publicly_visible}")
        print(f"is_publicly_viewable()={prop.is_publicly_viewable()}")
        print(f"URL: /accommodation/guest/{prop.slug}")
        if not prop.is_publicly_viewable():
            raise SystemExit("ERROR: property still not publicly viewable after provisioning")


if __name__ == "__main__":
    main()