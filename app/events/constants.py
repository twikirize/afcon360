
#app/events/constants.py
"""
Event-related constants and enums to avoid circular imports.
"""

import enum


class EventStatus(str, enum.Enum):
    DRAFT = 'draft'
    PENDING_APPROVAL = 'pending_approval'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    LIVE = 'live'
    PUBLISHED = 'published'
    SUSPENDED = 'suspended'
    PAUSED = 'paused'
    CANCELLED = 'cancelled'
    ARCHIVED = 'archived'
    DELETED = 'deleted'
