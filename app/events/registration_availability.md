# Event Registration Availability Contract

## State model

The public registration state is derived from the persisted `Event` dates,
registration window, ticket windows, ticket capacity, and current UTC time.
The state calculation is read-only; the database and the registration service
remain authoritative for accepting a booking.

| State | Predicate | Public behavior |
|---|---|---|
| `not_open` | The event is published, but `now` is before `registration_opens_at`, or every active ticket starts later. | Show the event and opening time; do not show a registration action. |
| `open` | The event is published, registration is required, at least one active ticket is currently available, and no close/expiry predicate is true. | Show ticket prices and registration action. |
| `closed` | The registration deadline or all currently valid ticket windows have passed, or the event is not eligible for public registration. | Show a closed message; never render a registration action. |
| `sold_out` | Event or all active ticket capacities are exhausted. | Show sold-out message; never render a registration action. |
| `expired` | `end_date` is before the current UTC calendar date. `end_date` is inclusive. | Show the expired template/message; never accept a registration. |

`expired` has precedence over every other state. If an event has no explicit
registration close, registration closes at the start of its `start_date`;
this prevents new tickets being sold after the event begins. An explicit close
may intentionally extend into a live event.

## Authority and invariants

- Organizers may set the registration opening and closing timestamps through
  the event create/edit workflow; the database rejects a reversed window.
- Public visitors may observe availability, but only authenticated users may
  initiate registration through the existing role/fresh-user boundary.
- The registration service recalculates availability with fresh database reads
  immediately before capacity/payment work. Cached availability is for public
  presentation only and is never an authorization or capacity decision.
- Successful registrations and cancellations invalidate the event availability
  cache; the cache also expires after a short TTL to track time boundaries.
- No registration is created when the state is `not_open`, `closed`,
  `sold_out`, or `expired`, including direct POST/API/service calls.

## Public past-event presentation contract

For a public event detail request, `is_past_event` is true exactly when the
availability state is `expired`. The public route must not query accommodation
inventory for a past event, and the landing page must satisfy these rules:

- Render one unambiguous `Event Ended` status and the event dates.
- Do not render registration or ticket-purchase links, community-host signup,
  countdown timers, seat-remaining counters, or live ticket availability.
- Replace booking-focused content with a short recap containing the total
  confirmed/checked-in registration count and a thank-you message.
- Keep descriptive event information available; hiding booking controls does
  not hide the public event record.

The state is calculated server-side from the cached presentation snapshot;
template conditionals are presentation safeguards only and do not replace the
fresh registration gate used by mutation routes.