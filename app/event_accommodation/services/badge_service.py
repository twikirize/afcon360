# app/event_accommodation/services/badge_service.py
"""
Badge Service - Manages event badge issuance, validation, and expiry.
"""

from datetime import datetime, timezone
from app.extensions import db
from app.event_accommodation.models.badge import EventBadge

class BadgeService:
    """Service for managing event participation badges."""

    @staticmethod
    def issue_badge(event_id: int, property_id: int, badge_type: str = "community_host", approved_by_id: int = None, starts_at: datetime = None, expires_at: datetime = None) -> EventBadge:
        """Issues an event badge for a property."""
        badge = EventBadge.query.filter_by(event_id=event_id, property_id=property_id).first()
        if badge:
            badge.badge_type = badge_type
            badge.approval_status = "approved"
            badge.approved_by = approved_by_id
            badge.approved_at = datetime.now(timezone.utc)
            badge.status = "active"
            if starts_at:
                badge.starts_at = starts_at
            if expires_at:
                badge.expires_at = expires_at
        else:
            badge = EventBadge(
                event_id=event_id,
                property_id=property_id,
                badge_type=badge_type,
                approval_status="approved",
                approved_by=approved_by_id,
                approved_at=datetime.now(timezone.utc),
                status="active",
                starts_at=starts_at,
                expires_at=expires_at
            )
            db.session.add(badge)
        
        db.session.commit()
        return badge

    @staticmethod
    def validate_badge(event_id: int, property_id: int) -> bool:
        """Checks if a property has an active, non-expired badge for an event."""
        badge = EventBadge.query.filter_by(event_id=event_id, property_id=property_id, status="active", approval_status="approved").first()
        if not badge:
            return False
        
        now = datetime.now(timezone.utc)
        if badge.expires_at and badge.expires_at < now:
            badge.status = "expired"
            db.session.commit()
            return False
            
        return True
