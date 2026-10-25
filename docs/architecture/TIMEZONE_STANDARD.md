# AFCON360 Timezone Standard

**Status:** implementation baseline established; repository-wide adoption and database migration remain in progress.

## Canonical contract

1. **Absolute instants are UTC.** Values that represent a real moment (creation, confirmation, expiry, payment, driver lifecycle and event instants) are stored and compared as UTC instants. PostgreSQL columns representing instants should be timezone-aware (TIMESTAMP WITH TIME ZONE / SQLAlchemy DateTime with timezone=True).
2. **Local time is a boundary representation.** Convert to a person's, venue's, or service location's IANA timezone only when interpreting user input or displaying a value. Never depend on the host operating system's local timezone.
3. **A naive datetime is not an instant.** Do not silently treat it as UTC or server-local time. An API should normally receive an ISO-8601 timestamp with Z or an explicit offset. A wall-clock schedule may be accepted only when an explicit IANA timezone accompanies it.
4. **Handle daylight-saving transitions explicitly.** Reject a nonexistent or ambiguous local wall time unless the user/API provides an offset that identifies the intended instant.
5. **Dates remain dates.** Birthdays, accounting dates, tournament dates and other calendar-only values should remain DATE/Python date, not be shifted through UTC.
6. **Recurring schedules require their timezone.** A recurring local-time rule must retain its IANA timezone; converting one occurrence to UTC is not sufficient to preserve the wall-clock rule over seasonal offset changes.
7. **One application API.** Use app.utils.time for UTC clock reads, awareness checks, UTC normalization, explicit-zone parsing and local display conversion. New code must not introduce datetime.utcnow(), unqualified datetime.now(), implicit naive-to-UTC coercion, or machine-local timezone assumptions.
8. **Database sessions use UTC.** The PostgreSQL session timezone is set to UTC so database-generated timestamp expressions are deterministic and timezone-aware columns display consistently.

## Rollout and safety gates

- The central helper and connection-session UTC setting are the initial enforcement foundation.
- Existing model declarations and migrations are not changed wholesale by a text substitution. Before altering timestamp column types, run a read-only catalog and row audit for every affected database and determine whether each naive value is stored UTC, local wall time, or a domain date/time.
- Schema changes must be delivered through reviewed, additive/expand-and-contract migrations with populated-data tests, backup/recovery evidence, parity checks and an explicit cutover gate. No production database is written by source-code work.
- Each domain migration must update its writers, readers, schemas, JSON serialization, comparisons, jobs and tests together. A column must not be changed in isolation while consumers continue to assume its previous semantics.
- Legacy naive values must not be mass-shifted without evidence of their intended timezone. Where historical meaning cannot be proven, retain the rows and define an explicit, documented disposition rather than guessing.
- APP_TZ is transitional compatibility for legacy input only. It is not a global timezone for users across the world. New scheduled booking input must identify its own intended timezone or provide an explicit offset.

## Current implementation scope

This branch adds the shared time primitives and pins PostgreSQL sessions to UTC. It does not claim that every existing model, migration, or call site has already been converted. Transport booking semantics, the shared timestamp mixin, schema migrations and the remaining legacy call sites require their own audited changes and regression gates.
