# app/events/constants.py
"""
EventStatus — the single source of truth for every state an event can be in.

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
created_by_type / created_by_id   — who pressed the "create" button; immutable.
current_owner_type / current_owner_id — who currently controls the event;
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

import enum


class EventStatus(str, enum.Enum):
    # ── Authoring ──────────────────────────────────────────────────────────
    DRAFT            = "draft"            # saved, not yet submitted

    # ── Moderation queue ───────────────────────────────────────────────────
    PENDING_APPROVAL = "pending_approval" # submitted, awaiting review
    APPROVED         = "approved"         # cleared, not yet live
    REJECTED         = "rejected"         # declined by moderator

    # ── Live ───────────────────────────────────────────────────────────────
    PUBLISHED        = "published"        # publicly visible, open for registration

    # ── Operational holds (reversible) ─────────────────────────────────────
    SUSPENDED        = "suspended"        # admin enforcement hold
    PAUSED           = "paused"           # organiser temporarily hides / pauses sales

    # ── Terminal positive ──────────────────────────────────────────────────
    COMPLETED        = "completed"        # end_date passed, ran successfully (auto)
    CANCELLED        = "cancelled"        # organiser cancelled before it ran

    # ── Terminal negative ──────────────────────────────────────────────────
    ARCHIVED         = "archived"         # organiser soft-deleted / post-completed archival
    DELETED          = "deleted"          # admin hard-removed (still in DB, never shown)

    # ── Legacy ─────────────────────────────────────────────────────────────
    # Keep for DB backward-compat only; never assign these in new code.
    ACTIVE           = "active"           # old alias for PUBLISHED


# ── Allowed state-machine transitions ─────────────────────────────────────────
# Key   = current status
# Value = set of statuses this event may transition INTO
ALLOWED_TRANSITIONS: dict[EventStatus, set[EventStatus]] = {
    EventStatus.DRAFT: {
        EventStatus.PENDING_APPROVAL,
        EventStatus.DELETED,
    },
    EventStatus.PENDING_APPROVAL: {
        EventStatus.APPROVED,
        EventStatus.REJECTED,
        EventStatus.DRAFT,           # moderator sends back for revision
        EventStatus.DELETED,
    },
    EventStatus.APPROVED: {
        EventStatus.PUBLISHED,
        EventStatus.REJECTED,
        EventStatus.DRAFT,
        EventStatus.DELETED,
    },
    EventStatus.REJECTED: {
        EventStatus.DRAFT,           # organiser revises and resubmits
        EventStatus.DELETED,
    },
    EventStatus.PUBLISHED: {
        EventStatus.SUSPENDED,
        EventStatus.PAUSED,
        EventStatus.COMPLETED,       # triggered by scheduler
        EventStatus.CANCELLED,
        EventStatus.APPROVED,        # unpublish
        EventStatus.DELETED,
    },
    EventStatus.SUSPENDED: {
        EventStatus.PUBLISHED,       # admin reactivates
        EventStatus.CANCELLED,
        EventStatus.DELETED,
    },
    EventStatus.PAUSED: {
        EventStatus.PUBLISHED,       # organiser resumes
        EventStatus.CANCELLED,
        EventStatus.DELETED,
    },
    EventStatus.COMPLETED: {
        EventStatus.ARCHIVED,        # after retention period
        EventStatus.DELETED,
    },
    EventStatus.CANCELLED: {
        EventStatus.ARCHIVED,        # clean up after window
        EventStatus.DELETED,
    },
    EventStatus.ARCHIVED: {
        EventStatus.DELETED,         # admin can escalate
    },
    EventStatus.DELETED: set(),      # terminal — no further transitions
    EventStatus.ACTIVE: {
        EventStatus.PUBLISHED,       # migrate legacy records
    },
}


# ── Visibility rules ───────────────────────────────────────────────────────────

# Statuses visible to the general public
PUBLIC_VISIBLE_STATUSES: frozenset[EventStatus] = frozenset({
    EventStatus.PUBLISHED,
})

# Statuses the organiser can see in their own dashboard
ORGANISER_VISIBLE_STATUSES: frozenset[EventStatus] = frozenset({
    EventStatus.DRAFT,
    EventStatus.PENDING_APPROVAL,
    EventStatus.APPROVED,
    EventStatus.REJECTED,
    EventStatus.PUBLISHED,
    EventStatus.SUSPENDED,
    EventStatus.PAUSED,
    EventStatus.COMPLETED,
    EventStatus.CANCELLED,
    EventStatus.ARCHIVED,
})

# Statuses only admins / system can see
ADMIN_ONLY_STATUSES: frozenset[EventStatus] = frozenset({
    EventStatus.DELETED,
})

# Statuses that still accept new registrations
REGISTRATION_OPEN_STATUSES: frozenset[EventStatus] = frozenset({
    EventStatus.PUBLISHED,
})

# Terminal statuses — no further organiser action possible
TERMINAL_STATUSES: frozenset[EventStatus] = frozenset({
    EventStatus.COMPLETED,
    EventStatus.CANCELLED,
    EventStatus.ARCHIVED,
    EventStatus.DELETED,
})


def validate_transition(current: EventStatus, target: EventStatus) -> tuple[bool, str]:
    """
    Validate whether a status transition is permitted.

    Returns (allowed: bool, reason: str).
    Callers should check `allowed` before persisting.
    """
    if current == target:
        return False, f"Event is already in status '{current.value}'."
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        return False, (
            f"Cannot transition from '{current.value}' to '{target.value}'. "
            f"Allowed targets: {[s.value for s in allowed] or 'none (terminal)'}."
        )
    return True, ""