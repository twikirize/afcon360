# app/accommodation/services/review_service.py
"""
Review Service - Handles review submission, moderation, and aggregation.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Tuple, Optional
from sqlalchemy import func
from app.extensions import db
from app.accommodation.models.review import Review, AccommodationReviewStatus
from app.accommodation.models.booking import AccommodationBooking, AccommodationBookingStatus
import logging

logger = logging.getLogger(__name__)


class ReviewService:
    """Service for managing accommodation reviews."""

    @staticmethod
    def submit_review(
        booking_id: int,
        reviewer_id: int,
        overall_rating: int,
        comment: str = None,
        cleanliness_rating: int = None,
        accuracy_rating: int = None,
        checkin_rating: int = None,
        communication_rating: int = None,
        location_rating: int = None,
        value_rating: int = None,
    ) -> Tuple[Optional[Review], Optional[str]]:
        """
        Submit a review for a booking.

        Returns:
            (review, error_message)
        """
        try:
            booking = db.session.get(AccommodationBooking, booking_id)
            if not booking:
                return None, "Booking not found"

            if booking.status != AccommodationBookingStatus.CHECKED_OUT.value:
                return None, "You can only review after check-out"

            if booking.booked_by_user_id != reviewer_id and booking.primary_guest_id != reviewer_id:
                return None, "Only the booker or primary guest can review this booking"

            existing = Review.query.filter_by(booking_id=booking_id).first()
            if existing:
                return None, "You have already reviewed this booking"

            review = Review(
                booking_id=booking_id,
                property_id=booking.property_id,
                reviewer_id=reviewer_id,
                overall_rating=overall_rating,
                comment=comment,
                cleanliness_rating=cleanliness_rating,
                accuracy_rating=accuracy_rating,
                checkin_rating=checkin_rating,
                communication_rating=communication_rating,
                location_rating=location_rating,
                value_rating=value_rating,
                status=AccommodationReviewStatus.PENDING.value,
            )
            db.session.add(review)
            db.session.commit()

            logger.info(f"Review submitted for booking {booking_id} by user {reviewer_id}")
            return review, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to submit review: {e}", exc_info=True)
            return None, str(e)

    @staticmethod
    def approve_review(review_id: int, moderator_id: int) -> Tuple[bool, Optional[str]]:
        """Approve a review and publish it."""
        try:
            review = db.session.get(Review, review_id)
            if not review:
                return False, "Review not found"

            review.publish(moderator_id)
            ReviewService._update_property_rating(review.property_id)
            db.session.commit()
            return True, None
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to approve review: {e}", exc_info=True)
            return False, str(e)

    @staticmethod
    def reject_review(review_id: int, moderator_id: int, reason: str) -> Tuple[bool, Optional[str]]:
        """Reject a review."""
        try:
            review = db.session.get(Review, review_id)
            if not review:
                return False, "Review not found"

            review.reject(moderator_id, reason)
            db.session.commit()
            return True, None
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to reject review: {e}", exc_info=True)
            return False, str(e)

    @staticmethod
    def respond_to_review(review_id: int, host_id: int, response_text: str) -> Tuple[bool, Optional[str]]:
        """Host responds to a published review."""
        try:
            review = db.session.get(Review, review_id)
            if not review:
                return False, "Review not found"

            if not review.is_published:
                return False, "Cannot respond to an unpublished review"

            # Verify host owns the property
            from app.accommodation.models.property import Property
            prop = db.session.get(Property, review.property_id)
            if not prop or not prop.is_owned_by(host_id):
                return False, "You do not own this property"

            review.respond(response_text)
            db.session.commit()
            return True, None
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to respond to review: {e}", exc_info=True)
            return False, str(e)

    @staticmethod
    def _update_property_rating(property_id: int) -> None:
        """Recalculate property average rating and review count."""
        from app.accommodation.models.property import Property
        avg = db.session.query(func.avg(Review.overall_rating)).filter(
            Review.property_id == property_id,
            Review.is_published.is_(True),
        ).scalar()
        count = db.session.query(func.count(Review.id)).filter(
            Review.property_id == property_id,
            Review.is_published.is_(True),
        ).scalar()

        prop = db.session.get(Property, property_id)
        if prop:
            prop.overall_rating = float(avg) if avg else None
            prop.total_reviews = count or 0
            db.session.add(prop)

    @staticmethod
    def get_property_reviews(property_id: int, page: int = 1, per_page: int = 10):
        """Get published reviews for a property."""
        return Review.query.filter(
            Review.property_id == property_id,
            Review.is_published.is_(True),
        ).order_by(Review.published_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def get_booking_review(booking_id: int) -> Optional[Review]:
        """Get review for a specific booking."""
        return Review.query.filter_by(booking_id=booking_id).first()

