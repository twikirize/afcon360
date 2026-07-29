# app/event_accommodation/services/invitation_service.py
"""
Invitation Service - Manages event host invitations to property owners.
"""

from app.extensions import db
from app.event_accommodation.models.badge import EventBadge

class InvitationService:
    """Service for inviting properties to participate in events."""

    @staticmethod
    def invite_property(event_id: int, property_id: int, badge_type: str = "community_host") -> EventBadge:
        """Invites a property to an event, creating a badge entry with status='invited'."""
        badge = EventBadge.query.filter_by(event_id=event_id, property_id=property_id).first()
        if not badge:
            badge = EventBadge(
                event_id=event_id,
                property_id=property_id,
                badge_type=badge_type,
                status="invited",
                approval_status="pending"
            )
            db.session.add(badge)
        else:
            badge.status = "invited"
        db.session.commit()
        return badge

    @staticmethod
    def respond_to_invitation(event_id: int, property_id: int, accept: bool) -> EventBadge:
        """Property owner responds to an event invitation."""
        badge = EventBadge.query.filter_by(event_id=event_id, property_id=property_id, status="invited").first()
        if not badge:
            raise ValueError("No pending invitation found for this property and event.")
            
        if accept:
            badge.status = "accepted"
            badge.approval_status = "approved"
        else:
            badge.status = "revoked"
            badge.approval_status = "rejected"
            
        db.session.commit()
        return badge
