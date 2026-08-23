# app/events/constants.py
"""
EventStatus - the single source of truth for every state an event can be in.

LIFECYCLE
─────────────────────────────────────────────────────────────────────────────
                         ┌──────────────┐
                         │    DRAFT     │  created but not submitted
                         └──────┬───────┘
                                │ submit()
                         ┌──────▼───────┐
                         │  PENDING_    │  awaiting moderation
                         │  APPROVAL   │
                         └──────┬───────┘
              ┌─────────────────┼──────────────────┐
         approve()          reject()          (auto or admin)
              │                  │                  │
       ┌──────▼──────┐   ┌───────▼──────┐          │
       │  APPROVED   │   │   REJECTED   │          │
       └──────┬───────┘   └──────────────┘          │
         publish()                                   │
       ┌──────▼──────┐                              │
       │  PUBLISHED  │◄─────────────────────────────┘
       └──────┬───────┘   unpublish() → back to APPROVED
              │
    ┌─────────┼──────────┬─────────────┐
 suspend()  pause()  end_date passes  cancel()
    │          │           │              │
┌───▼────┐ ┌──▼─────┐ ┌───▼───────┐ ┌───▼───────┐
│SUSPEND-│ │ PAUSED │ │ COMPLETED │ │ CANCELLED │
│  ED    │ └──┬─────┘ └───┬───────┘ └───┬───────┘
└───┬────┘ resume()       │ (+90d)       │
    │reactivate()    ┌────▼──────┐       │
    └────────────►   │  ARCHIVED │◄──────┘
                     └────┬──────┘
                   admin  │  hard_remove()
                     ┌────▼──────┐
                     │  DELETED  │  soft-only, never physical
                     └───────────┘


DRAFT → PENDING_APPROVAL → APPROVED → PUBLISHED → COMPLETED → ARCHIVED
                                ↓           ↓           ↓
                            REJECTED    SUSPENDED   CANCELLED
                                ↓        PAUSED         ↓
                            DELETED        ↓         ARCHIVED
                                       PUBLISHED        ↓
                                                      DELETED
RULES
─────
1.  PostgreSQL is the source of truth.  No event is ever physically removed.
2.  DELETED is the terminal state for admin-removed events.
3.  ARCHIVED is the terminal state for organiser-soft-deleted events.
4.  COMPLETED is the terminal state for events that ran successfully.
5.  Moderation / financial logs are append-only and reference event by id,
    so they survive even after the event reaches DELETED.
6.  Expired events (end_date < today) are transitioned by a scheduled job,
    not by user action.

CREATOR vs OWNER
─────────────────
created_by_type / created_by_id   - who pressed the "create" button; immutable.
current_owner_type / current_owner_id - who currently controls the event;
                                        can change via EventTransferRequest.

Examples:
  • You (manager) create an event on behalf of a client:
      created_by_type=INDIVIDUAL, created_by_id=<your id>
      current_owner_type=INDIVIDUAL, current_owner_id=<client id>

  • System auto-creates its anniversary event:
      created_by_type=SYSTEM, created_by_id=0
      current_owner_type=SYSTEM, current_owner_id=0

  • Admin creates a system event:
      created_by_type=INDIVIDUAL, created_by_id=<admin id>
      current_owner_type=SYSTEM, current_owner_id=0
      is_system_event=True
"""

from enum import Enum
from typing import List, Tuple, Set


def _status_value(value):
    """
    Normalize either an EventStatus enum member or a plain string to the
    database string value used in ALLOWED_TRANSITIONS.
    """
    return getattr(value, "value", value)


class EventStatus(str, Enum):
    """
    Event status values - stored as strings in DB, validated in code.
    This is the ONLY place status values are defined.
    """
    # Authoring
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"

    # Moderation
    APPROVED = "approved"
    REJECTED = "rejected"

    # Live
    PUBLISHED = "published"

    # Operational holds
    SUSPENDED = "suspended"
    PAUSED = "paused"

    # Terminal positive
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    # Terminal negative
    ARCHIVED = "archived"
    DELETED = "deleted"

    # Legacy (kept for backward compatibility)
    ACTIVE = "active"

    @classmethod
    def choices(cls) -> List[Tuple[str, str]]:
        """Return list of (value, label) pairs for form selects."""
        return [(status.value, status.value.replace('_', ' ').title())
                for status in cls if status != cls.ACTIVE]

    @classmethod
    def values(cls) -> List[str]:
        """Return all valid status values."""
        return [s.value for s in cls]

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Check if a string value is a valid status."""
        return value in cls.values()

    @classmethod
    def get_publishable_statuses(cls) -> List[str]:
        """Return statuses that can eventually be published."""
        return [cls.APPROVED.value, cls.DRAFT.value]

    @classmethod
    def get_active_statuses(cls) -> List[str]:
        """Return statuses that represent active/live events."""
        return [cls.PUBLISHED.value, cls.APPROVED.value]

    @classmethod
    def get_terminal_statuses(cls) -> Set[str]:
        """Return statuses that are terminal (no further changes)."""
        return {
            cls.COMPLETED.value,
            cls.CANCELLED.value,
            cls.ARCHIVED.value,
            cls.DELETED.value,
        }

    @classmethod
    def can_register(cls, status: str) -> bool:
        """Check if event accepts new registrations."""
        return status == cls.PUBLISHED.value

    @classmethod
    def needs_moderation(cls, status: str) -> bool:
        """Check if event needs moderator review."""
        return status == cls.PENDING_APPROVAL.value

    @classmethod
    def get_archivable_from(cls) -> List[str]:
        """
        Return statuses from which ARCHIVED is allowed.

        Useful for the service layer when the current route wants an organiser
        soft-delete (target_status=ARCHIVED).
        """
        return [
            status
            for status, targets in ALLOWED_TRANSITIONS.items()
            if cls.ARCHIVED.value in targets
        ]

    @classmethod
    def get_hard_deletable_from(cls) -> List[str]:
        """
        Return statuses from which DELETED is allowed.

        Useful for service-level super-admin hard-delete paths.
        """
        return [
            status
            for status, targets in ALLOWED_TRANSITIONS.items()
            if cls.DELETED.value in targets
        ]


class RegistrationAvailability(str, Enum):
    """Public registration-window states derived from event data and time."""

    NOT_OPEN = "not_open"
    OPEN = "open"
    CLOSED = "closed"
    SOLD_OUT = "sold_out"
    EXPIRED = "expired"


# Allowed state transitions - single source of truth.
#
# The service layer must NOT define its own copy of this map.
# Import ALLOWED_TRANSITIONS and validate_transition from this module instead.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    EventStatus.DRAFT.value: {
        EventStatus.PENDING_APPROVAL.value,
        EventStatus.ARCHIVED.value,
        EventStatus.DELETED.value,
    },
    EventStatus.PENDING_APPROVAL.value: {
        EventStatus.APPROVED.value,
        EventStatus.REJECTED.value,
        EventStatus.DRAFT.value,
        EventStatus.ARCHIVED.value,
        EventStatus.DELETED.value,
    },
    EventStatus.APPROVED.value: {
        EventStatus.PUBLISHED.value,
        EventStatus.REJECTED.value,
        EventStatus.DRAFT.value,
        EventStatus.ARCHIVED.value,
        EventStatus.DELETED.value,
    },
    EventStatus.REJECTED.value: {
        EventStatus.DRAFT.value,
        EventStatus.ARCHIVED.value,
        EventStatus.DELETED.value,
    },
    EventStatus.PUBLISHED.value: {
        EventStatus.SUSPENDED.value,
        EventStatus.PAUSED.value,
        EventStatus.COMPLETED.value,
        EventStatus.CANCELLED.value,
        EventStatus.APPROVED.value,
        EventStatus.ARCHIVED.value,
        EventStatus.DELETED.value,
    },
    EventStatus.SUSPENDED.value: {
        EventStatus.PUBLISHED.value,
        EventStatus.CANCELLED.value,
        EventStatus.ARCHIVED.value,
        EventStatus.DELETED.value,
    },
    EventStatus.PAUSED.value: {
        EventStatus.PUBLISHED.value,
        EventStatus.CANCELLED.value,
        EventStatus.ARCHIVED.value,
        EventStatus.DELETED.value,
    },
    EventStatus.COMPLETED.value: {
        EventStatus.ARCHIVED.value,
        EventStatus.DELETED.value,
    },
    EventStatus.CANCELLED.value: {
        EventStatus.ARCHIVED.value,
        EventStatus.DELETED.value,
    },
    EventStatus.ARCHIVED.value: {
        EventStatus.DELETED.value,
    },
    EventStatus.DELETED.value: set(),
    EventStatus.ACTIVE.value: {
        EventStatus.PUBLISHED.value,
    },
}


def validate_transition(current: str, target: str) -> tuple[bool, str]:
    """
    Validate whether a status transition is permitted.

    Accepts either EventStatus enum members or database string values.

    Returns (allowed: bool, reason: str).
    """
    current = _status_value(current)
    target = _status_value(target)

    if current == target:
        return False, f"Event is already in status '{current}'."

    if current not in ALLOWED_TRANSITIONS:
        return False, f"Unknown current status: '{current}'"

    allowed = ALLOWED_TRANSITIONS[current]
    if target not in allowed:
        allowed_str = ', '.join(sorted(allowed)) if allowed else 'none (terminal)'
        return False, f"Cannot transition from '{current}' to '{target}'. Allowed: {allowed_str}"

    return True, ""


class BookingType(str, Enum):
    """Who the registration is for, relative to who submitted the form."""
    SELF = "self"
    THIRD_PARTY = "third_party"
    GROUP = "group"

    @classmethod
    def values(cls) -> List[str]:
        return [b.value for b in cls]

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in cls.values()

    @classmethod
    def choices(cls):
        return [(bt.value, bt.value.replace('_', ' ').title()) for bt in cls]


# Group size limits
MAX_INLINE_GROUP_SIZE = 25  # Maximum attendees per inline form submission
MAX_BULK_GROUP_SIZE = 500    # Maximum for bulk upload (Phase 5)