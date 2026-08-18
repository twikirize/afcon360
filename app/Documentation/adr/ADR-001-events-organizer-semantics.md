# ADR 001: Events Organizer Semantics & Compatibility

**Date:** 2026-08-15
**Status:** Accepted
**Context:** Phase 2, Step 4 of the Events Identity & Context Migration

## Context and Problem Statement
The `Event` model contains `organizer_id`, `created_by_id`/`created_by_type`, and `current_owner_id`/`current_owner_type`. During the migration to a unified context and identity framework, the exact canonical meaning of `organizer_id` was ambiguous. Characterization tests revealed that the system uses `organizer_id` inside `_is_event_owner` to grant "organiser" and owner-level permissions, alongside the explicit `current_owner_*` fields.

If we simply deprecate or remove `organizer_id` immediately, we risk breaking legacy events, ticketing workflows, moderation rules, and assignments that depend on this inferred ownership behavior. We cannot assume `current_owner_*` is the sole truth until all legacy records are migrated and all consumers are updated.

## Decision
1. **Preserve `organizer_id` behavior in `_is_event_owner`**: For Phase 2, `organizer_id` will continue to grant ownership-level authority for backward compatibility. 
2. **Canonical Forward Path**: `current_owner_type` and `current_owner_id` represent the true canonical ownership. New events and transferred events will strictly populate and use the explicit `current_owner_*` fields.
3. **No Context Bypass**: The active operating context (`active_context_id`) will explicitly limit authority based on roles, but will *never* implicitly map to or overwrite `organizer_id` or `current_owner_id`.
4. **Future Deprecation (Phase 3/4)**: We will write a future database migration to backfill `current_owner_id` using `organizer_id` for legacy records, after which `organizer_id` will be officially repurposed as purely the "operational contact" or completely deprecated.

## Consequences
- **Positive:** Zero breakage for existing events and workflows. 
- **Positive:** Clear pathway to migrate away from implicit ownership logic to explicit polymorphic ownership without introducing authorization bugs today.
- **Negative:** `permissions.py` continues to check two parallel fields (`organizer_id` and `current_owner_id`) for ownership resolution during the interim phases.
