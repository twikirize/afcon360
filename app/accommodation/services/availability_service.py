# app/accommodation/services/availability_service.py
"""
Availability Service - Check date availability and block/unblock dates
"""

from datetime import date, timedelta
from typing import List, Optional, Tuple
from sqlalchemy import and_
from app.extensions import db
from app.accommodation.models.availability import BlockedDate, AccommodationBlockedReason
from app.accommodation.models.booking import AccommodationBooking, AccommodationBookingStatus
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
            logger.debug(f"Date {check_date} blocked for property {property_id}: {blocked.reason.value}")
            return False

        # Check confirmed bookings that cover this date
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
    def block_dates(
            property_id: int,
            check_in: date,
            check_out: date,
            reason: AccommodationBlockedReason,
            booking_id: int = None,
            created_by: int = None
    ) -> int:
        """
        Block a range of dates for a property.

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
    def unblock_dates(
            property_id: int,
            check_in: date,
            check_out: date,
            booking_id: int = None
    ) -> int:
        """
        Unblock a range of dates for a property.

        Returns:
            Number of dates unblocked
        """
        query = BlockedDate.query.filter(
            BlockedDate.property_id == property_id,
            BlockedDate.blocked_date.between(check_in, check_out - timedelta(days=1))
        )

        if booking_id:
            query = query.filter(BlockedDate.booking_id == booking_id)

        result = query.delete(synchronize_session=False)
        db.session.commit()

        logger.info(f"Unblocked {result} dates for property {property_id} (booking: {booking_id})")
        return result

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