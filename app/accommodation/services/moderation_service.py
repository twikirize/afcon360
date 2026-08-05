# app/accommodation/services/moderation_service.py

from typing import Tuple, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from app.extensions import db
from app.accommodation.models.property import Property
from app.accommodation.models.moderation import PropertyModerationHistory
from app.services.notification_service import NotificationService
import logging

logger = logging.getLogger(__name__)


class ModerationService:
    """
    Complete moderation service for property lifecycle management.
    Handles all moderation actions with proper notifications and audit trails.
    """

    # Status transition rules
    VALID_TRANSITIONS = {
        'draft': ['submitted', 'archived'],
        'submitted': ['under_review', 'approved', 'needs_information', 'rejected', 'archived'],
        'pending_review': ['under_review', 'approved', 'needs_information', 'rejected', 'archived'],
        'under_review': ['approved', 'needs_information', 'rejected', 'archived'],
        'approved': ['published', 'suspended', 'archived'],
        'needs_information': ['submitted', 'archived'],
        'published': ['suspended', 'archived'],
        'active': ['suspended', 'archived'],  # Legacy support
        'suspended': ['pending_review', 'archived'],
        'archived': ['draft'],  # Restore from soft-delete archive
    }

    # Status display names for notifications / templates
    STATUS_DISPLAY = {
        'draft': 'Draft',
        'submitted': 'Submitted for Review',
        'pending_review': 'Pending Review',
        'under_review': 'Under Review',
        'approved': 'Approved',
        'needs_information': 'Needs Information',
        'published': 'Published',
        'active': 'Active',
        'suspended': 'Suspended',
        'archived': 'Archived',
        'rejected': 'Rejected',
    }

    @staticmethod
    def _get_owner_id(property_obj: Property) -> Optional[int]:
        """Get the user ID of the property owner (handles both individual and organisation)."""
        if property_obj.owner_user_id:
            return property_obj.owner_user_id
        elif property_obj.owner_org_id:
            from app.identity.models.organisation import Organisation
            org = db.session.get(Organisation, property_obj.owner_org_id)
            if org:
                return org.primary_contact_user_id
        return None

    @staticmethod
    def _get_owner_email(property_obj: Property) -> Optional[str]:
        """Get the email of the property owner."""
        if property_obj.owner_user_id:
            return property_obj.owner_user.email if property_obj.owner_user else None
        elif property_obj.owner_org_id:
            from app.identity.models.organisation import Organisation
            org = db.session.get(Organisation, property_obj.owner_org_id)
            if org:
                return org.email
        return None

    @staticmethod
    def _can_transition(property_obj: Property, target_status: str) -> Tuple[bool, str]:
        """Check if a status transition is valid."""
        current = property_obj.status
        if current == target_status:
            return False, f"Property is already in {target_status} status."
        if target_status not in ModerationService.VALID_TRANSITIONS.get(current, []):
            return False, f"Cannot transition from '{current}' to '{target_status}'."
        return True, ""

    @staticmethod
    def _log_action(
        property_id: int,
        action: str,
        previous_status: str,
        new_status: str,
        moderator_id: int,
        reason: str = None,
        notes: str = None
    ) -> PropertyModerationHistory:
        """Create a moderation history entry."""
        history = PropertyModerationHistory(
            property_id=property_id,
            action=action,
            previous_status=previous_status,
            new_status=new_status,
            reason=reason,
            moderated_by=moderator_id,
            notes=notes
        )
        db.session.add(history)
        return history

    @staticmethod
    def _send_notification(
        user_id: int,
        notification_type: str,
        title: str,
        message: str,
        property_title: str = None
    ):
        """Send notification with proper error handling."""
        try:
            if user_id:
                NotificationService.send(
                    user_id=user_id,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    channels=['in_app', 'email']
                )
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

    # ====================================================================
    # CORE MODERATION ACTIONS
    # ====================================================================

    @staticmethod
    def approve_property(property_id: int, moderator_id: int, notes: str = None) -> Tuple[bool, Optional[str]]:
        """
        Approve a property - moves to APPROVED status.
        Property must be in submitted, pending_review, or under_review.
        """
        prop = db.session.get(Property, property_id)
        if not prop:
            return False, "Property not found."

        # Check if property is in reviewable state
        if prop.status not in ['pending_review', 'under_review', 'submitted']:
            return False, f"Property is in '{prop.status}' status. Only submitted/under_review properties can be approved."

        # Check transition validity
        valid, msg = ModerationService._can_transition(prop, 'approved')
        if not valid:
            return False, msg

        previous_status = prop.status

        # Update property
        prop.status = 'approved'
        prop.is_verified = True
        prop.verification_status = 'verified'
        prop.verified_at = datetime.now(timezone.utc)
        prop.verified_by = moderator_id

        # Log action
        history = ModerationService._log_action(
            property_id=property_id,
            action='approved',
            previous_status=previous_status,
            new_status='approved',
            moderator_id=moderator_id,
            notes=notes
        )

        db.session.commit()

        # Send notifications
        owner_id = ModerationService._get_owner_id(prop)
        if owner_id:
            ModerationService._send_notification(
                user_id=owner_id,
                notification_type='property_approved',
                title='✅ Property Approved!',
                message=f'Your property "{prop.title}" has been approved by the moderator. Click "Publish" to make it live.'
            )

        logger.info(f"Property {property_id} ({prop.title}) approved by moderator {moderator_id}")
        return True, None

    @staticmethod
    def publish_property(property_id: int, moderator_id: int, notes: str = None) -> Tuple[bool, Optional[str]]:
        """
        Publish a property - moves to PUBLISHED status.
        Property must be in APPROVED status and pass readiness checks.
        """
        prop = db.session.get(Property, property_id)
        if not prop:
            return False, "Property not found."

        if prop.status != 'approved':
            return False, f"Property is in '{prop.status}' status. Only approved properties can be published."

        # Check transition validity
        valid, msg = ModerationService._can_transition(prop, 'published')
        if not valid:
            return False, msg

        # Check readiness
        from app.accommodation.services.readiness_service import AccommodationReadinessService
        can_book, failures = AccommodationReadinessService.check_readiness(prop)
        if not can_book:
            return False, f"Property not ready for publication: {', '.join(failures)}"

        previous_status = prop.status

        # Update property
        prop.status = 'published'
        prop.is_publicly_visible = True
        prop.is_verified = True
        prop.published_at = datetime.now(timezone.utc)

        # Log action
        history = ModerationService._log_action(
            property_id=property_id,
            action='published',
            previous_status=previous_status,
            new_status='published',
            moderator_id=moderator_id,
            notes=notes
        )

        db.session.commit()

        # Send notifications
        owner_id = ModerationService._get_owner_id(prop)
        if owner_id:
            ModerationService._send_notification(
                user_id=owner_id,
                notification_type='property_published',
                title='🎉 Your Property is Now Live!',
                message=f'Your property "{prop.title}" is now publicly visible and ready for bookings!'
            )

        logger.info(f"Property {property_id} ({prop.title}) published by moderator {moderator_id}")
        return True, None

    @staticmethod
    def reject_property(property_id: int, moderator_id: int, reason: str, notes: str = None) -> Tuple[bool, Optional[str]]:
        """
        Reject a property - moves to DRAFT status with rejection reason.
        Property must be in submitted, under_review, or pending_review.
        """
        prop = db.session.get(Property, property_id)
        if not prop:
            return False, "Property not found."

        if prop.status not in ['pending_review', 'under_review', 'submitted']:
            return False, f"Property is in '{prop.status}' status. Only reviewable properties can be rejected."

        # Check transition validity
        valid, msg = ModerationService._can_transition(prop, 'rejected')
        if not valid:
            return False, msg

        previous_status = prop.status

        # Update property
        prop.status = 'draft'
        prop.verification_status = 'rejected'
        prop.verification_notes = reason

        # Log action
        history = ModerationService._log_action(
            property_id=property_id,
            action='rejected',
            previous_status=previous_status,
            new_status='draft',
            moderator_id=moderator_id,
            reason=reason,
            notes=notes
        )

        db.session.commit()

        # Send notifications
        owner_id = ModerationService._get_owner_id(prop)
        if owner_id:
            ModerationService._send_notification(
                user_id=owner_id,
                notification_type='property_rejected',
                title='📝 Property Rejected',
                message=f'Your property "{prop.title}" was rejected. Reason: {reason}. Please make the necessary changes and resubmit.'
            )

        logger.info(f"Property {property_id} ({prop.title}) rejected by moderator {moderator_id}")
        return True, None

    @staticmethod
    def request_changes(property_id: int, moderator_id: int, changes: str, notes: str = None) -> Tuple[bool, Optional[str]]:
        """
        Request changes for a property - moves to NEEDS_INFORMATION status.
        Property must be in submitted, under_review, or pending_review.
        """
        prop = db.session.get(Property, property_id)
        if not prop:
            return False, "Property not found."

        if prop.status not in ['pending_review', 'under_review', 'submitted']:
            return False, f"Property is in '{prop.status}' status. Only reviewable properties can be sent back for changes."

        # Check transition validity
        valid, msg = ModerationService._can_transition(prop, 'needs_information')
        if not valid:
            return False, msg

        previous_status = prop.status

        # Update property
        prop.status = 'needs_information'
        prop.verification_status = 'pending'
        prop.moderation_notes = changes

        # Log action
        history = ModerationService._log_action(
            property_id=property_id,
            action='changes_requested',
            previous_status=previous_status,
            new_status='needs_information',
            moderator_id=moderator_id,
            reason=changes,
            notes=notes
        )

        db.session.commit()

        # Send notifications
        owner_id = ModerationService._get_owner_id(prop)
        if owner_id:
            ModerationService._send_notification(
                user_id=owner_id,
                notification_type='property_changes_requested',
                title='📝 Property Needs Updates',
                message=f'Changes requested for "{prop.title}": {changes}. Please update and resubmit.'
            )

        logger.info(f"Changes requested for property {property_id} ({prop.title}) by moderator {moderator_id}")
        return True, None

    @staticmethod
    def suspend_property(property_id: int, moderator_id: int, reason: str, notes: str = None) -> Tuple[bool, Optional[str]]:
        """
        Suspend a property - moves to SUSPENDED status.
        Can be applied to active, published, or approved properties.
        """
        prop = db.session.get(Property, property_id)
        if not prop:
            return False, "Property not found."

        if prop.status not in ['active', 'published', 'approved']:
            return False, f"Property is in '{prop.status}' status. Only active, published, or approved properties can be suspended."

        # Check transition validity
        valid, msg = ModerationService._can_transition(prop, 'suspended')
        if not valid:
            return False, msg

        previous_status = prop.status

        # Update property
        prop.status = 'suspended'
        prop.is_active = False
        prop.verification_status = 'rejected'
        prop.suspension_reason = reason

        # Log action
        history = ModerationService._log_action(
            property_id=property_id,
            action='suspended',
            previous_status=previous_status,
            new_status='suspended',
            moderator_id=moderator_id,
            reason=reason,
            notes=notes
        )

        db.session.commit()

        # Send notifications
        owner_id = ModerationService._get_owner_id(prop)
        if owner_id:
            ModerationService._send_notification(
                user_id=owner_id,
                notification_type='property_suspended',
                title='⚠️ Property Suspended',
                message=f'Your property "{prop.title}" has been suspended. Reason: {reason}. Please contact support for more information.'
            )

        logger.info(f"Property {property_id} ({prop.title}) suspended by moderator {moderator_id}")
        return True, None

    @staticmethod
    def reinstate_property(property_id: int, moderator_id: int, notes: str = None) -> Tuple[bool, Optional[str]]:
        """
        Reinstate a suspended property - moves to PENDING_REVIEW status.
        Only applies to suspended properties.
        """
        prop = db.session.get(Property, property_id)
        if not prop:
            return False, "Property not found."

        if prop.status != 'suspended':
            return False, f"Property is in '{prop.status}' status. Only suspended properties can be reinstated."

        # Check transition validity
        valid, msg = ModerationService._can_transition(prop, 'pending_review')
        if not valid:
            return False, msg

        previous_status = prop.status

        # Update property
        prop.status = 'pending_review'
        prop.is_active = True
        prop.verification_status = 'pending'
        prop.suspension_reason = None

        # Log action
        history = ModerationService._log_action(
            property_id=property_id,
            action='reinstated',
            previous_status=previous_status,
            new_status='pending_review',
            moderator_id=moderator_id,
            notes=notes
        )

        db.session.commit()

        # Send notifications
        owner_id = ModerationService._get_owner_id(prop)
        if owner_id:
            ModerationService._send_notification(
                user_id=owner_id,
                notification_type='property_reinstated',
                title='✅ Property Reinstated',
                message=f'Your property "{prop.title}" has been reinstated and is now under review.'
            )

        logger.info(f"Property {property_id} ({prop.title}) reinstated by moderator {moderator_id}")
        return True, None

    @staticmethod
    def archive_property(property_id: int, moderator_id: int, reason: str, notes: str = None) -> Tuple[bool, Optional[str]]:
        """
        Archive a property - soft-delete to ARCHIVED status.
        Data is retained and can be restored via restore_archived_property.
        """
        prop = db.session.get(Property, property_id)
        if not prop:
            return False, "Property not found."

        if prop.status == 'archived':
            return False, "Property is already archived."

        # Check transition validity
        valid, msg = ModerationService._can_transition(prop, 'archived')
        if not valid:
            return False, msg

        if not reason or not str(reason).strip():
            return False, "A reason is required to archive a property."

        previous_status = prop.status
        now = datetime.now(timezone.utc)

        # Soft-delete + archive audit trail
        prop.status = 'archived'
        prop.is_active = False
        prop.is_publicly_visible = False
        prop.is_deleted = True
        prop.deleted_at = now
        prop.archived_reason = reason.strip()
        prop.archived_at = now
        prop.archived_by = moderator_id

        # Log action
        ModerationService._log_action(
            property_id=property_id,
            action='archived',
            previous_status=previous_status,
            new_status='archived',
            moderator_id=moderator_id,
            reason=reason.strip(),
            notes=notes
        )

        db.session.commit()

        # Send notifications
        owner_id = ModerationService._get_owner_id(prop)
        if owner_id:
            ModerationService._send_notification(
                user_id=owner_id,
                notification_type='property_archived',
                title='📦 Property Archived',
                message=(
                    f'Your property "{prop.title}" has been archived and is no longer publicly visible. '
                    f'Reason: {reason.strip()}'
                )
            )

        logger.info(f"Property {property_id} ({prop.title}) archived by moderator {moderator_id}")
        return True, None

    @staticmethod
    def restore_archived_property(
        property_id: int,
        moderator_id: int,
        notes: str = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Restore an archived property back to draft status.
        Clears soft-delete flags so the host can edit and resubmit.
        """
        prop = db.session.get(Property, property_id)
        if not prop:
            return False, "Property not found."

        if prop.status != 'archived':
            return False, f"Property is in '{prop.status}' status. Only archived properties can be restored."

        valid, msg = ModerationService._can_transition(prop, 'draft')
        if not valid:
            return False, msg

        previous_status = prop.status

        prop.status = 'draft'
        prop.is_active = True
        prop.is_deleted = False
        prop.deleted_at = None
        prop.is_publicly_visible = False
        prop.archived_reason = None
        prop.archived_at = None
        prop.archived_by = None

        ModerationService._log_action(
            property_id=property_id,
            action='restored',
            previous_status=previous_status,
            new_status='draft',
            moderator_id=moderator_id,
            notes=notes
        )

        db.session.commit()

        owner_id = ModerationService._get_owner_id(prop)
        if owner_id:
            ModerationService._send_notification(
                user_id=owner_id,
                notification_type='property_restored',
                title='♻️ Property Restored',
                message=(
                    f'Your property "{prop.title}" has been restored from archive to draft. '
                    f'You can edit it and resubmit for review.'
                )
            )

        logger.info(f"Property {property_id} ({prop.title}) restored from archive by moderator {moderator_id}")
        return True, None

    # ====================================================================
    # QUERY METHODS
    # ====================================================================

    @staticmethod
    def get_pending_properties(page: int = 1, per_page: int = 20):
        """Get all properties that need moderation attention."""
        return Property.query.filter(
            Property.status.in_(['pending_review', 'submitted', 'under_review', 'needs_information'])
        ).order_by(Property.created_at.asc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

    @staticmethod
    def get_pending_count() -> Dict[str, int]:
        """Get counts of properties in each review status."""
        statuses = ['pending_review', 'submitted', 'under_review', 'needs_information']
        counts = {}
        for status in statuses:
            counts[status] = Property.query.filter_by(status=status).count()
        counts['total'] = sum(counts.values())
        return counts

    @staticmethod
    def get_moderation_history(property_id: int):
        """Get full moderation history for a property."""
        return PropertyModerationHistory.query.filter_by(property_id=property_id).order_by(
            PropertyModerationHistory.created_at.desc()
        ).all()

    @staticmethod
    def get_property_status_display(property_obj: Property) -> str:
        """Get human-readable status display name."""
        return ModerationService.STATUS_DISPLAY.get(property_obj.status, property_obj.status)

    @staticmethod
    def get_property_status_color(property_obj: Property) -> str:
        """Get status color for UI (Bootstrap badge color names)."""
        color_map = {
            'draft': 'secondary',
            'submitted': 'primary',
            'pending_review': 'primary',
            'under_review': 'warning',
            'approved': 'info',
            'needs_information': 'danger',
            'published': 'success',
            'active': 'success',
            'suspended': 'danger',
            'archived': 'secondary',
            'rejected': 'danger',
        }
        return color_map.get(property_obj.status, 'secondary')

    @staticmethod
    def get_available_actions(property_obj: Property) -> list:
        """Get available moderation actions for a property based on its current status."""
        actions = []
        status = property_obj.status

        if status in ['submitted', 'under_review', 'pending_review']:
            actions.extend([
                {'action': 'approve', 'label': 'Approve', 'icon': 'check-lg', 'color': 'success'},
                {'action': 'request_changes', 'label': 'Request Changes', 'icon': 'pencil', 'color': 'warning'},
                {'action': 'reject', 'label': 'Reject', 'icon': 'x-lg', 'color': 'danger'},
            ])

        if status == 'approved':
            actions.extend([
                {'action': 'publish', 'label': 'Publish', 'icon': 'globe', 'color': 'success'},
                {'action': 'suspend', 'label': 'Suspend', 'icon': 'ban', 'color': 'danger'},
            ])

        if status in ['active', 'published']:
            actions.extend([
                {'action': 'suspend', 'label': 'Suspend', 'icon': 'ban', 'color': 'danger'},
            ])

        if status == 'suspended':
            actions.append(
                {'action': 'reinstate', 'label': 'Reinstate', 'icon': 'arrow-counterclockwise', 'color': 'info'}
            )

        if status == 'archived':
            actions.append(
                {'action': 'restore', 'label': 'Restore', 'icon': 'arrow-counterclockwise', 'color': 'info'}
            )
        else:
            # Archive is available for any non-archived property (single entry)
            actions.append(
                {'action': 'archive', 'label': 'Archive', 'icon': 'archive', 'color': 'secondary'}
            )

        return actions
