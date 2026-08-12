# app/accommodation/services/availability_service.py
"""
Availability Service - Check date availability and block/unblock dates
"""

from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple
from sqlalchemy import and_
from app.extensions import db
from app.accommodation.models.availability import BlockedDate, RoomHold, AccommodationBlockedReason
from app.accommodation.models.booking import AccommodationBooking, AccommodationBookingStatus
from app.accommodation.models.room import RoomType, InventoryBlock
import logging

logger = logging.getLogger(__name__)


class AvailabilityService:
    """
    Handles property availability checking and date blocking
    """

    @staticmethod
    def is_date_available(
            property_id: int,
            check_date: date,
            exclude_booking_id: int = None
    ) -> bool:
        """
        Check if a specific date is available for a property.

        Args:
            property_id: The property ID
            check_date: The date to check
            exclude_booking_id: Optional booking ID to exclude from the check (for confirming own booking)

        Returns:
            True if available, False if blocked or booked
        """
        # Check manually blocked dates
        blocked = BlockedDate.query.filter(
            BlockedDate.property_id == property_id,
            BlockedDate.blocked_date == check_date
        ).first()

        if blocked:
            # If this block belongs to the booking we're confirming, it's OK
            if exclude_booking_id and blocked.booking_id == exclude_booking_id:
                logger.debug(
                    f"Date {check_date} blocked by current booking {exclude_booking_id}, considering available")
                return True
            logger.debug(f"Date {check_date} blocked for property {property_id}: {blocked.reason}")
            return False

        # Check RoomType availability if RoomTypes exist
        from app.accommodation.models.room import RoomType
        room_types = RoomType.query.filter_by(property_id=property_id, is_active=True).all()
        if room_types:
            from app.accommodation.services.host_service import HostService
            any_available = False
            for rt in room_types:
                if HostService.available_units(rt.id, check_date, check_date + timedelta(days=1), exclude_booking_id=exclude_booking_id) > 0:
                    any_available = True
                    break
            if not any_available:
                logger.debug(f"No room types have available units on {check_date} for property {property_id}")
                return False
        else:
            # Check confirmed bookings that cover this date (legacy fallback)
            query = AccommodationBooking.query.filter(
                AccommodationBooking.property_id == property_id,
                AccommodationBooking.status.in_([
                    AccommodationBookingStatus.CONFIRMED.value,
                    AccommodationBookingStatus.CHECKED_IN.value
                ]),
                AccommodationBooking.check_in <= check_date,
                AccommodationBooking.check_out > check_date
            )

            # Exclude the current booking if we're checking for confirmation
            if exclude_booking_id:
                query = query.filter(AccommodationBooking.id != exclude_booking_id)

            booking = query.first()

            if booking:
                logger.debug(f"Date {check_date} booked for property {property_id} by booking {booking.booking_reference}")
                return False

        # Check availability rules (recurring rules)
        from app.accommodation.models.availability import AvailabilityRule
        rules = AvailabilityRule.query.filter(
            AvailabilityRule.property_id == property_id
        ).all()

        for rule in rules:
            if rule.applies_to_date(check_date):
                logger.debug(f"Date {check_date} affected by rule: available={rule.is_available}")
                return rule.is_available

        return True

    @staticmethod
    def is_range_available(
            property_id: int,
            check_in: date,
            check_out: date,
            exclude_booking_id: int = None
    ) -> Tuple[bool, List[date], Optional[str]]:
        """
        Check if a date range is available.

        Args:
            property_id: The property ID
            check_in: Start date
            check_out: End date
            exclude_booking_id: Optional booking ID to exclude from the check

        Returns:
            (is_available, blocked_dates, first_unavailable_reason)
        """
        blocked_dates = []
        current_date = check_in

        while current_date < check_out:
            if not AvailabilityService.is_date_available(property_id, current_date, exclude_booking_id):
                blocked_dates.append(current_date)
            current_date += timedelta(days=1)

        if blocked_dates:
            return False, blocked_dates, f"Dates {blocked_dates[0]} not available"

        return True, [], None

    @staticmethod
    def get_room_type_availability(
        property_id: int,
        check_in: date,
        check_out: date,
        num_guests: int = 2,
        num_rooms: int = 1,
        exclude_booking_id: int = None
    ) -> dict:
        """
        Get detailed availability for all room types at a property.

        Returns count-based availability per room type, with capacity matching.
        """
        from app.accommodation.models.room import RoomType
        from app.accommodation.services.host_service import HostService
        from datetime import timedelta

        room_types = RoomType.query.filter_by(property_id=property_id, is_active=True).all()
        results = []

        for rt in room_types:
            available = HostService.available_units(rt.id, check_in, check_out, exclude_booking_id)
            rooms_needed = max(1, (num_guests + rt.max_guests - 1) // rt.max_guests) if num_guests > 0 else num_rooms
            can_accommodate = rt.max_guests >= num_guests or rooms_needed <= available

            blocked_dates = []
            current_date = check_in
            while current_date < check_out:
                units_for_date = HostService.available_units(rt.id, current_date, current_date + timedelta(days=1), exclude_booking_id)
                if units_for_date <= 0:
                    blocked_dates.append(current_date.isoformat())
                current_date += timedelta(days=1)

            status = "available" if (available >= num_rooms and can_accommodate) else (
                "limited" if available > 0 else "sold_out"
            )
            if blocked_dates and available > 0:
                status = "partial"

            results.append({
                'id': rt.id,
                'name': rt.name,
                'max_guests': rt.max_guests,
                'total_units': rt.total_units,
                'available_units': available,
                'is_available': available >= num_rooms,
                'can_accommodate_guests': can_accommodate,
                'rooms_needed': rooms_needed,
                'status': status,
                'price': float(rt.base_price_per_night),
                'currency': rt.currency,
                'blocked_dates': blocked_dates,
            })

        return {'room_types': results, 'property_id': property_id}

    @staticmethod
    def get_availability_cascade(
        property_id: int,
        check_in: date,
        check_out: date,
        num_guests: int = 2,
        num_rooms: int = 1,
        exclude_booking_id: int = None
    ) -> dict:
        """
        Full availability cascade: Tier 0 → Tier 1 → Tier 2.

        Tier 0: Exact room type match
        Tier 1: Same-property alternative room types
        Tier 2: Context-aware nearby properties
        """
        from app.accommodation.models.property import Property
        from app.accommodation.services.host_service import HostService

        prop = db.session.get(Property, property_id)
        if not prop:
            return {'error': 'Property not found'}

        # Get room type availability
        rt_availability = AvailabilityService.get_room_type_availability(
            property_id, check_in, check_out, num_guests, num_rooms, exclude_booking_id
        )

        # Tier 0: Exact match (all room types that are fully available)
        tier0 = [rt for rt in rt_availability['room_types'] if rt['is_available'] and rt['can_accommodate_guests']]

        # Tier 1: Same property alternatives (room types that can partially accommodate)
        tier1 = [rt for rt in rt_availability['room_types'] if not rt['is_available'] and rt['can_accommodate_guests'] and rt['available_units'] > 0]

        # Tier 2: Nearby properties (context-aware)
        tier2 = []
        if not tier0 and not tier1:
            tier2 = AvailabilityService.find_nearby_alternatives(property_id, check_in, check_out, num_guests, num_rooms)

        # Partial availability info
        partial = None
        for rt in rt_availability['room_types']:
            if rt['status'] == 'partial':
                # Find earliest available date after blocked dates
                from datetime import timedelta
                avail_from = None
                current = check_in
                while current < check_out:
                    units = HostService.available_units(rt['id'], current, current + timedelta(days=1), exclude_booking_id)
                    if units > 0 and avail_from is None:
                        avail_from = current.isoformat()
                    current += timedelta(days=1)
                partial = {
                    'room_type_id': rt['id'],
                    'name': rt['name'],
                    'blocked_dates': rt['blocked_dates'],
                    'available_from': avail_from,
                    'available_units': rt['available_units'],
                    'message': f'Booked until {rt["blocked_dates"][-1] if rt["blocked_dates"] else "N/A"}. Available from {avail_from or "immediately"}.'
                }
                break

        return {
            'property_id': property_id,
            'property_name': prop.title if hasattr(prop, 'title') else str(prop),
            'check_in': check_in.isoformat(),
            'check_out': check_out.isoformat(),
            'guest_count': num_guests,
            'rooms_requested': num_rooms,
            'tier0_exact_match': tier0,
            'tier1_same_property': tier1,
            'tier2_nearby_properties': tier2,
            'partial_availability': partial,
            'room_types': rt_availability['room_types'],
        }

    @staticmethod
    def find_nearby_alternatives(
        property_id: int,
        check_in: date,
        check_out: date,
        num_guests: int,
        num_rooms: int,
        radius_km: float = 10.0
    ) -> list:
        """
        Find nearby properties with matching availability, ranked by:
        1. Event/venue proximity (if context available)
        2. Amenity overlap
        3. Price band proximity
        4. Distance
        5. Rating
        """
        from app.accommodation.models.property import Property
        from app.accommodation.services.host_service import HostService
        from sqlalchemy import func

        prop = db.session.get(Property, property_id)
        if not prop:
            return []

        nearby = []
        # Simple distance-based search using approximate km from lat/lng
        lat_range = (prop.latitude - radius_km / 111, prop.latitude + radius_km / 111) if prop.latitude else None
        lng_range = (prop.longitude - radius_km / 111, prop.longitude + radius_km / 111) if prop.longitude else None

        query = Property.query.filter(
            Property.id != property_id,
            Property.is_active == True,
            Property.is_verified == True,
        )
        if lat_range and lng_range:
            query = query.filter(
                Property.latitude.between(lat_range[0], lat_range[1]),
                Property.longitude.between(lng_range[0], lng_range[1]),
            )

        for p in query.limit(20).all():
            rt_result = AvailabilityService.get_room_type_availability(
                p.id, check_in, check_out, num_guests, num_rooms
            )
            available_rts = [rt for rt in rt_result['room_types'] if rt['is_available'] and rt['can_accommodate_guests']]
            if available_rts:
                distance = None
                if prop.latitude and p.latitude:
                    from math import radians, cos, sin, asin, sqrt
                    lon1, lat1, lon2, lat2 = map(radians, [prop.longitude, prop.latitude, p.longitude, p.latitude])
                    dlon = lon2 - lon1
                    dlat = lat2 - lat1
                    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
                    distance = round(2 * asin(sqrt(a)) * 6371, 1)

                nearby.append({
                    'id': p.id,
                    'name': p.title,
                    'distance_km': distance,
                    'room_type': available_rts[0],
                    'reason': f'{distance}km away, {len(available_rts)} room type(s) available',
                })

        nearby.sort(key=lambda x: (x['distance_km'] or 99999))
        return nearby[:5]

    @staticmethod
    def block_dates(
            property_id: int,
            check_in: date,
            check_out: date,
            reason: AccommodationBlockedReason,
            booking_id: int = None,
            created_by: int = None,
            expires_at: datetime = None
    ) -> int:
        """
        Block a range of dates for a property.

        Args:
            property_id: The property ID
            check_in: Start date
            check_out: End date (exclusive)
            reason: Block reason enum
            booking_id: Optional booking ID to associate
            created_by: User ID who created the block
            expires_at: Optional expiration datetime for automatic cleanup

        Returns:
            Number of dates blocked
        """
        blocked_count = 0
        current_date = check_in

        while current_date < check_out:
            # Check if already blocked
            existing = BlockedDate.query.filter(
                BlockedDate.property_id == property_id,
                BlockedDate.blocked_date == current_date
            ).first()

            if not existing:
                blocked = BlockedDate(
                    property_id=property_id,
                    blocked_date=current_date,
                    reason=reason,
                    booking_id=booking_id,
                    created_by=created_by
                )
                db.session.add(blocked)
                blocked_count += 1
                logger.debug(f"Blocked date {current_date} for property {property_id}")

            current_date += timedelta(days=1)

        db.session.commit()
        logger.info(f"Blocked {blocked_count} dates for property {property_id} (booking: {booking_id})")
        return blocked_count

    @staticmethod
    def create_hold(
            property_id: int,
            check_in: date,
            check_out: date,
            created_by: int,
            room_type_id: int = None,
            units: int = 1,
            hold_minutes: int = 15,
            hold_type: str = "payment",
            approval_sla_hours: int = 48,
    ) -> Tuple[bool, Optional[str]]:
        """
        Create a temporary hold on dates (pre-booking hold).

        For single-unit properties: uses BlockedDate (property-wide)
        For multi-unit hotels: uses InventoryBlock (room-type scoped)

        Args:
            property_id: The property ID
            check_in: Start date
            check_out: End date (exclusive)
            created_by: User ID creating the hold
            room_type_id: Room type ID for multi-unit properties
            units: Number of rooms/units to hold
            hold_minutes: How long the hold lasts before auto-release (payment holds)
            hold_type: "payment" (15 min) or "approval" (approval_sla_hours)
            approval_sla_hours: Hours before approval hold expires

        Returns:
            (success, error_message)
        """
        try:
            from datetime import datetime, timezone

            if hold_type == "approval":
                expires_at = datetime.now(timezone.utc) + timedelta(hours=approval_sla_hours)
                effective_minutes = approval_sla_hours * 60
            else:
                expires_at = datetime.now(timezone.utc) + timedelta(minutes=hold_minutes)
                effective_minutes = hold_minutes

            # Determine if this is a multi-unit property
            is_multi_unit = False
            if room_type_id:
                from app.accommodation.models.room import RoomType
                room_type = db.session.get(RoomType, room_type_id)
                if room_type and room_type.total_units > 1:
                    is_multi_unit = True

            if is_multi_unit and room_type_id:
                # Multi-unit: use InventoryBlock for room-type-scoped blocking
                available = AvailabilityService.get_available_units(
                    room_type_id, check_in, check_out
                )
                if available < units:
                    return False, f"Only {available} unit(s) available, requested {units}"

                block = InventoryBlock(
                    room_type_id=room_type_id,
                    date_range_start=check_in,
                    date_range_end=check_out,
                    units_blocked=units,
                    reason=AccommodationBlockedReason.TEMPORARY_HOLD.value,
                    booking_id=None,  # Will be set later when booking is created
                    created_by=created_by,
                )
                db.session.add(block)
                db.session.flush()
            else:
                # Single-unit: use property-wide BlockedDate
                blocked_count = AvailabilityService.block_dates(
                    property_id=property_id,
                    check_in=check_in,
                    check_out=check_out,
                    reason=AccommodationBlockedReason.TEMPORARY_HOLD,
                    created_by=created_by,
                    expires_at=expires_at
                )

                if blocked_count == 0:
                    return False, "Dates are already on hold"

            # Create RoomHold record for tracking/expiration
            hold = RoomHold(
                property_id=property_id,
                room_type_id=room_type_id,
                check_in=check_in,
                check_out=check_out,
                guest_user_id=created_by,
                units=units,
                hold_minutes=effective_minutes,
                expires_at=expires_at,
                status="active",
                hold_type=hold_type,
                approval_sla_hours=approval_sla_hours if hold_type == "approval" else None,
            )
            db.session.add(hold)
            db.session.flush()

            logger.info(
                f"Temporary {hold_type} hold created for property {property_id} "
                f"by user {created_by} ({check_in} → {check_out})"
            )
            return True, hold.id

        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to create hold for property {property_id}: {e}")
            return False, "Could not hold dates. Please try again."

    @staticmethod
    def release_hold(
            property_id: int,
            check_in: date,
            check_out: date,
            created_by: int = None
    ) -> int:
        """
        Release a temporary hold on dates.

        Args:
            property_id: The property ID
            check_in: Start date
            check_out: End date (exclusive)
            created_by: Optional user ID who created the hold

        Returns:
            Number of dates released
        """
        query = BlockedDate.query.filter(
            BlockedDate.property_id == property_id,
            BlockedDate.blocked_date.between(check_in, check_out - timedelta(days=1)),
            BlockedDate.reason == AccommodationBlockedReason.TEMPORARY_HOLD.value
        )

        if created_by:
            query = query.filter(BlockedDate.created_by == created_by)

        result = query.delete(synchronize_session=False)

        hold_query = RoomHold.query.filter(
            RoomHold.property_id == property_id,
            RoomHold.check_in == check_in,
            RoomHold.check_out == check_out,
            RoomHold.status == "active",
        )
        if created_by:
            hold_query = hold_query.filter(RoomHold.guest_user_id == created_by)
        for hold in hold_query.all():
            hold.mark_released("Released by checkout flow")

        db.session.commit()

        logger.info(f"Released {result} temporary holds for property {property_id}")
        return result

    @staticmethod
    def release_expired_holds(hold_minutes: int = 15) -> int:
        """
        Release temporary holds that have expired.

        Args:
            hold_minutes: Maximum age of payment holds before they're considered expired.
                          Approval holds use their own approval_sla_hours.

        Returns:
            Number of expired holds released
        """
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        # Expire old BlockedDate-based holds (legacy cleanup)
        expired_time = now - timedelta(minutes=hold_minutes)

        expired_blocked = BlockedDate.query.filter(
            BlockedDate.reason == AccommodationBlockedReason.TEMPORARY_HOLD.value,
            BlockedDate.created_at < expired_time
        ).all()

        count = len(expired_blocked)
        for hold in expired_blocked:
            db.session.delete(hold)

        # Expire RoomHold records
        expired_room_holds = RoomHold.query.filter(
            RoomHold.status == "active",
            RoomHold.expires_at <= now,
        ).all()

        for hold in expired_room_holds:
            if hold.hold_type == "approval":
                # Approval holds expire based on approval_sla_hours
                if hold.approval_sla_hours and hold.expires_at <= now:
                    hold.mark_expired()
                    count += 1
            else:
                # Payment holds expire based on hold_minutes
                hold.mark_expired()
                count += 1

        db.session.commit()

        if count > 0:
            logger.info(f"Released {count} expired temporary holds")

        return count

    @staticmethod
    def unblock_dates(
            property_id: int,
            check_in: date,
            check_out: date,
            booking_id: int = None,
            reason: str = None
    ) -> int:
        """
        Unblock a range of dates for a property.

        Args:
            property_id: The property ID
            check_in: Start date
            check_out: End date (exclusive)
            booking_id: Optional booking ID to filter by
            reason: Optional reason to filter by (e.g., 'temporary_hold')

        Returns:
            Number of dates unblocked
        """
        query = BlockedDate.query.filter(
            BlockedDate.property_id == property_id,
            BlockedDate.blocked_date.between(check_in, check_out - timedelta(days=1))
        )

        if booking_id:
            query = query.filter(BlockedDate.booking_id == booking_id)

        if reason:
            query = query.filter(BlockedDate.reason == reason)

        result = query.delete(synchronize_session=False)
        db.session.commit()

        logger.info(f"Unblocked {result} dates for property {property_id} (booking: {booking_id}, reason: {reason})")
        return result


    @staticmethod
    def expire_room_holds(now: datetime = None) -> int:
        """Expire active RoomHold records and release their temporary inventory blocks."""
        now = now or datetime.now(timezone.utc)
        expired_holds = RoomHold.query.filter(
            RoomHold.status == "active",
            RoomHold.expires_at <= now,
        ).all()

        expired_count = 0
        for hold in expired_holds:
            BlockedDate.query.filter(
                BlockedDate.property_id == hold.property_id,
                BlockedDate.blocked_date.between(hold.check_in, hold.check_out - timedelta(days=1)),
                BlockedDate.reason == AccommodationBlockedReason.TEMPORARY_HOLD.value,
                BlockedDate.created_by == hold.guest_user_id,
            ).delete(synchronize_session=False)

            if hold.room_type_id:
                AvailabilityService.release_room_type_blocks(
                    room_type_id=hold.room_type_id,
                    check_in=hold.check_in,
                    check_out=hold.check_out,
                    booking_id=hold.booking_id,
                )

            hold.mark_expired()
            expired_count += 1

        db.session.commit()
        logger.info(f"Expired {expired_count} room holds")
        return expired_count

    @staticmethod
    def get_available_dates(
            property_id: int,
            start_date: date,
            end_date: date,
            max_dates: int = 90
    ) -> List[date]:
        """
        Get all available dates within a range.
        """
        available_dates = []
        current_date = start_date
        end_limit = min(end_date, start_date + timedelta(days=max_dates))

        while current_date <= end_limit:
            if AvailabilityService.is_date_available(property_id, current_date):
                available_dates.append(current_date)
            current_date += timedelta(days=1)

        return available_dates

    @staticmethod
    def get_available_units(
            room_type_id: int,
            check_in: date,
            check_out: date,
            exclude_booking_id: int = None,
    ) -> int:
        """
        Calculate available units for a room type on a date range.

        Formula: total_units - confirmed_bookings - inventory_blocks
        """
        room_type = db.session.get(RoomType, room_type_id)
        if not room_type:
            return 0

        available = room_type.total_units

        # Subtract confirmed/checked-in bookings overlapping the date range
        booking_query = AccommodationBooking.query.filter(
            AccommodationBooking.room_type_id == room_type_id,
            AccommodationBooking.status.in_([
                AccommodationBookingStatus.CONFIRMED.value,
                AccommodationBookingStatus.CHECKED_IN.value,
            ]),
            AccommodationBooking.check_in < check_out,
            AccommodationBooking.check_out > check_in,
        )
        if exclude_booking_id:
            booking_query = booking_query.filter(AccommodationBooking.id != exclude_booking_id)

        booked = booking_query.count()
        available -= booked

        # Subtract inventory blocks (maintenance, seasonal, etc.)
        blocks = InventoryBlock.query.filter(
            InventoryBlock.room_type_id == room_type_id,
            InventoryBlock.date_range_start < check_out,
            InventoryBlock.date_range_end > check_in,
        ).all()
        for block in blocks:
            available -= block.units_blocked

        return max(0, available)

    @staticmethod
    def is_room_type_available(
            room_type_id: int,
            check_in: date,
            check_out: date,
            requested_units: int = 1,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a room type has enough available units for a date range.
        """
        available = AvailabilityService.get_available_units(room_type_id, check_in, check_out)

        if available >= requested_units:
            return True, None

        return False, f"Only {available} unit(s) available, but {requested_units} requested"

    @staticmethod
    def block_room_type_units(
            room_type_id: int,
            check_in: date,
            check_out: date,
            units_to_block: int = 1,
            reason: str = AccommodationBlockedReason.BOOKED.value,
            booking_id: Optional[int] = None,
            created_by: Optional[int] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Block units for a room type for a date range.

        Creates or updates an InventoryBlock record for the room type.
        """
        try:
            room_type = db.session.get(RoomType, room_type_id)
            if not room_type:
                return False, "Room type not found"

            # Check if enough units are available
            available = AvailabilityService.get_available_units(room_type_id, check_in, check_out)
            if available < units_to_block:
                return False, f"Insufficient units: {available} available, {units_to_block} requested"

            # Always create a distinct inventory block for this booking/hold request
            block = InventoryBlock(
                room_type_id=room_type_id,
                booking_id=booking_id,
                date_range_start=check_in,
                date_range_end=check_out,
                units_blocked=units_to_block,
                reason=reason,
                created_by=created_by,
            )
            db.session.add(block)

            db.session.commit()
            return True, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to block room type units for room_type {room_type_id}: {e}")
            return False, str(e)

    @staticmethod
    def release_room_type_blocks(
            room_type_id: int,
            check_in: date,
            check_out: date,
            booking_id: Optional[int] = None,
    ) -> int:
        """
        Release inventory blocks for a room type on a date range.

        If booking_id is provided, only release blocks belonging to that booking.
        Returns the number of blocks released.
        """
        query = InventoryBlock.query.filter(
            InventoryBlock.room_type_id == room_type_id,
            InventoryBlock.date_range_start == check_in,
            InventoryBlock.date_range_end == check_out,
        )

        if booking_id:
            query = query.filter(InventoryBlock.booking_id == booking_id)

        result = query.delete(synchronize_session=False)
        db.session.commit()

        if result > 0:
            logger.info(f"Released {result} inventory block(s) for room_type {room_type_id} on {check_in} to {check_out}")

        return result

