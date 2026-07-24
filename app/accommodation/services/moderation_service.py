from typing import Tuple, Optional
from datetime import datetime, timezone
from app.extensions import db
from app.accommodation.models.property import Property
from app.accommodation.models.moderation import PropertyModerationHistory
from app.services.notification_service import NotificationService

class ModerationService:
    @staticmethod
    def approve_property(property_id: int, moderator_id: int, notes: str = None) -> Tuple[bool, Optional[str]]:
        prop = Property.query.get(property_id)
        if not prop or prop.status != 'pending_review':
            return False, "Property not found or not in pending status."
        
        previous_status = prop.status
        prop.status = 'active'
        prop.is_verified = True
        prop.is_active = True
        prop.verification_status = 'verified'
        prop.verified_at = datetime.now(timezone.utc)
        prop.verified_by = moderator_id
        
        history = PropertyModerationHistory(
            property_id=property_id,
            action='approved',
            previous_status=previous_status,
            new_status='active',
            moderated_by=moderator_id,
            notes=notes
        )
        
        db.session.add(history)
        db.session.commit()
        NotificationService.send(
            user_id=prop.host_id,
            notification_type='property_approved',
            title='🎉 Your Property is Live!',
            message=f'Your property "{prop.title}" has been approved and is now visible to guests.',
            channels=['in_app', 'email']
        )
        return True, None

    @staticmethod
    def reject_property(property_id: int, moderator_id: int, reason: str, notes: str = None) -> Tuple[bool, Optional[str]]:
        prop = Property.query.get(property_id)
        if not prop:
            return False, "Property not found."
            
        previous_status = prop.status
        prop.status = 'draft'
        prop.verification_status = 'rejected'
        prop.verification_notes = reason
        
        history = PropertyModerationHistory(
            property_id=property_id,
            action='rejected',
            previous_status=previous_status,
            new_status='draft',
            reason=reason,
            moderated_by=moderator_id,
            notes=notes
        )
        
        db.session.add(history)
        db.session.commit()
        NotificationService.send(
            user_id=prop.host_id,
            notification_type='property_rejected',
            title='📝 Property Needs Changes',
            message=f'Your property "{prop.title}" was rejected. Reason: {reason}',
            channels=['in_app', 'email']
        )
        return True, None

    @staticmethod
    def request_changes(property_id: int, moderator_id: int, changes: str, notes: str = None) -> Tuple[bool, Optional[str]]:
        prop = Property.query.get(property_id)
        if not prop:
            return False, "Property not found."
            
        previous_status = prop.status
        prop.status = 'draft'
        prop.verification_status = 'pending'
        prop.moderation_notes = changes
        
        history = PropertyModerationHistory(
            property_id=property_id,
            action='changes_requested',
            previous_status=previous_status,
            new_status='draft',
            reason=changes,
            moderated_by=moderator_id,
            notes=notes
        )
        
        db.session.add(history)
        db.session.commit()
        NotificationService.send(
            user_id=prop.host_id,
            notification_type='property_changes_requested',
            title='📝 Property Needs Updates',
            message=f'Requested changes for "{prop.title}": {changes}',
            channels=['in_app', 'email']
        )
        return True, None

    @staticmethod
    def suspend_property(property_id: int, moderator_id: int, reason: str, notes: str = None) -> Tuple[bool, Optional[str]]:
        prop = Property.query.get(property_id)
        if not prop:
            return False, "Property not found."
            
        previous_status = prop.status
        prop.status = 'suspended'
        prop.is_active = False
        prop.verification_status = 'rejected'
        
        history = PropertyModerationHistory(
            property_id=property_id,
            action='suspended',
            previous_status=previous_status,
            new_status='suspended',
            reason=reason,
            moderated_by=moderator_id,
            notes=notes
        )
        
        db.session.add(history)
        db.session.commit()
        NotificationService.send(
            user_id=prop.host_id,
            notification_type='property_suspended',
            title='⚠️ Property Suspended',
            message=f'Your property "{prop.title}" has been suspended. Reason: {reason}',
            channels=['in_app', 'email']
        )
        return True, None

    @staticmethod
    def reinstate_property(property_id: int, moderator_id: int, notes: str = None) -> Tuple[bool, Optional[str]]:
        prop = Property.query.get(property_id)
        if not prop:
            return False, "Property not found."
            
        previous_status = prop.status
        prop.status = 'pending_review'
        
        history = PropertyModerationHistory(
            property_id=property_id,
            action='reinstated',
            previous_status=previous_status,
            new_status='pending_review',
            moderated_by=moderator_id,
            notes=notes
        )
        
        db.session.add(history)
        db.session.commit()
        NotificationService.send(
            user_id=prop.host_id,
            notification_type='property_reinstated',
            title='✅ Property Reinstated',
            message=f'Your property "{prop.title}" has been reinstated and is now under review.',
            channels=['in_app', 'email']
        )
        return True, None

    @staticmethod
    def get_pending_properties(page: int = 1, per_page: int = 20):
        return Property.query.filter_by(status='pending_review').paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def get_moderation_history(property_id: int):
        return PropertyModerationHistory.query.filter_by(property_id=property_id).order_by(
            PropertyModerationHistory.created_at.desc()
        ).all()
