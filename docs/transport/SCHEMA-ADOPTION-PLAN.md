# AFCON360 — Schema Adoption Plan

Status: PLANNED (not started)
Owner: TBD
Related: app/transport/routes.py (dead BookingSchema import), BACKLOG.md
Last updated: 2026-10-11

## 1. Purpose

Define where validation schemas live in AFCON360, how they are rolled out
across every domain, and how they are enforced safely — so that a rider's
form is checked at the API boundary before it reaches any service layer,
in every module, without ever breaking a working client.

This document is for the engineer who will build it. It states the
decisions already made and the rollout sequence already agreed. It does
not require the reader to re-litigate placement.

## 2. Current state

- `app/schemas/` now exists. It is **Pydantic-native** (Pydantic 2.10.0,
  already in the stack — no new dependency) with a thin
  marshmallow-shaped adapter in `app/schemas/common.py` so calling code
  keeps the `schema.load(...)` / `ValidationError.messages` surface.
- `app/transport/routes.py` imports `from app.schemas.transport import
  BookingSchema`. The schema is wired in **shadow mode** behind
  `TRANSPORT_BOOKING_SCHEMA_ENFORCE` (default `False`).
- No other module has a schema of any kind. Validation today is scattered
  across service-layer helpers (`validate_booking_request`,
  `_validate_booking_location_coordinates`, `validate_driver_registration`,
  `validate_vehicle_registration`, `validate_organisation_transport`).
- Service-layer validation works, but it is the "clerk", not the "front
  desk". A malformed field travels all the way into the service before
  being rejected.

## 3. Target architecture

Schemas live **per domain, at the API boundary**. Not in `utils/`. Not
attached to models.

    app/
      schemas/
        __init__.py
        common.py           # BaseSchema adapter + ValidationError (Pydantic-backed)
        transport.py        # BookingSchema, VehicleRegistrationSchema,
                            #   DriverRegistrationSchema, OfferAcceptSchema,
                            #   TripActionSchema, CancellationSchema,
                            #   RetryMatchingSchema, RideOptionsSchema
        accommodation.py    # GuestRegistrationSchema, PropertySchema, ...
        events.py           # EventCreateSchema, TicketPurchaseSchema, ...
        wallet.py           # DepositSchema, WithdrawalSchema, TransferSchema
        identity.py         # ProfileUpdateSchema, KYCSubmissionSchema
        tourism.py
        feed.py

### Rules

1. One file per domain. No file exceeds ~400 lines; split into
   `transport/bookings.py` etc. only if a domain grows.
2. Every schema subclasses `app.schemas.common.BaseSchema` and sets a
   Pydantic `Model`. Set `model_config = ConfigDict(extra="ignore")`
   (never reject unknown fields — see §5.3).
3. Schemas describe the **API boundary**, never the DB row. A model may
   have zero, one, or many schemas depending on how many distinct payload
   shapes it accepts.
4. Schemas never import SQLAlchemy models. They operate on primitive
   types. If a schema needs to know "is this user_id a real user", that
   is a service-layer check, not a schema check.
5. Schemas never write to the database. They parse and validate.
6. `utils/` is for domain-agnostic helpers only. If a helper is only used
   by one schema, it lives in `common.py`; if it is used by none, it does
   not live in `utils/`.
7. **String preservation:** `BaseSchema.load()` returns the original
   values, not Pydantic's coerced output. Services re-parse strings; the
   schema is a gate, not a transformer.

## 4. Why not the alternatives

- **`app/utils/schema.py` (one giant file)** — rejected. Merge conflicts
  on every PR; import cycles with models; blast radius = whole app;
  discoverability collapses past 20 schemas. No production system uses
  this.
- **Attached to each model** — rejected. Model files become API-contract
  files; they change on the DB clock, not the API clock; one model needs
  up to five schemas (Create / Update / Admin / Public / Search).
- **Per-module `app/transport/schemas.py`** — valid pattern (DRF, Django
  Ninja use it), but rejected here because `routes.py` already imports
  `app.schemas.transport`. The original author chose B; we finish it.
- **Marshmallow** — rejected on 2026-10-11. Not installed; Pydantic 2.10.0
  is the project's validation stack (AGENTS.md §24). The adapter keeps the
  marshmallow-shaped calling convention without the dependency.

## 5. Safe rollout — the six steps (do not skip any)

Applying a schema too early breaks production. Follow these in order for
every domain.

### 5.1 Shadow mode first

Add the schema and call `.load(payload)` on every request. **Do not enforce
the result.** Log every failure as
`SCHEMA-SHADOW domain=<name> errors=<list>`. Pass the original payload
through unchanged.

Run shadow mode for at least one week of representative traffic.

### 5.2 Mirror the service-layer rules — add nothing new

The schema must contain **exactly** the checks the service already
performs, no more. Enumerate them by reading the service:

- Transport: `validate_booking_request`,
  `_validate_booking_location_coordinates`, coordinate ranges,
  `ServiceType`, `ProviderType`, `Currency`, `VehicleClass`, and the
  `_extract_coords` rules.
- Repeat for each domain.

If the service accepts a payload today, the schema must accept it too.
This is the single most important rule.

### 5.3 Unknown fields are excluded, never rejected

Set `extra="ignore"` (Pydantic) / `Meta.unknown = EXCLUDE` (marshmallow).
Clients that send extra fields (analytics tags, `utm_source`,
future-signed payload fields) must keep working exactly as they do now.

### 5.4 Replay historical payloads

Before enabling enforcement:

1. Capture a week of request bodies from the access log.
2. Run every one through the schema.
3. Assert **zero** rejections.
4. Any rejection is a bug — either the schema is wrong or a real client
   is wrong. Investigate both, do not assume.

### 5.5 Enforce behind a config flag

    TRANSPORT_BOOKING_SCHEMA_ENFORCE = false    # dev default
    ACCOMMODATION_SCHEMA_ENFORCE     = false
    # ... one flag per domain per endpoint

Flag lives in `app/config.py::Config` and is read through
`current_app.config.get(...)` (never from root `config.py`, which the app
factory does not load). Flip in dev, then staging, then production. If
anything breaks, flip back. No deploy needed.

### 5.6 Keep a one-cycle passthrough window

For one release after enforcement is on, log any rejection at WARNING
before returning 400. Operate on that signal. After one release with no
unexpected rejections, remove the passthrough.

## 6. Where each domain's schemas come from

Map existing service-layer validators to future schemas:

| Domain | Service validators today | Future schema file |
|---|---|---|
| transport | `validate_booking_request`, `validate_driver_registration`, `validate_vehicle_registration`, `validate_organisation_transport` | `app/schemas/transport.py` |
| accommodation | (list validators in `app/accommodation/services/*`) | `app/schemas/accommodation.py` |
| events | (list validators in `app/events/services/*`) | `app/schemas/events.py` |
| wallet | (list validators in `app/wallet/services/*`) | `app/schemas/wallet.py` |
| identity | (list validators in `app/identity/services/*`) | `app/schemas/identity.py` |
| tourism | (list validators) | `app/schemas/tourism.py` |
| feed | (list validators) | `app/schemas/feed.py` |

Note: this table is intentionally incomplete — the future engineer must
fill in the right-hand column domain by domain, in the order of highest
traffic / highest risk first.

## 7. Order of adoption (recommended)

1. **Transport — BookingSchema** (already has a dead import; highest
   traffic).
2. **Identity — ProfileUpdateSchema, KYCSubmissionSchema** (KYC is
   regulated, precision matters).
3. **Wallet — Deposit, Withdrawal, Transfer** (money-adjacent; gate on
   regulatory review).
4. **Accommodation — GuestRegistration, Property**.
5. **Events — EventCreate, TicketPurchase**.
6. Everything else.

Do not start a second domain until the first has passed through step 5.6.

## 8. Tests required per domain

- Unit: schema accepts the exact payload the service accepts (parse the
  service's validator outputs, replay them through the schema, assert
  equality).
- Unit: schema rejects malformed payloads with field-specific errors.
- Integration: shadow-mode log has zero rejections across a full
  pytest session.
- Regression: with the flag off, HTTP behavior is identical to pre-schema.
- Regression: with the flag on, the original happy-path test still passes.
- Failure injection: one field removed → 400 with a useful message.

## 9. Anti-patterns — do not do these

- Do not put schemas in `utils/`.
- Do not attach them to SQLAlchemy models.
- Do not enforce a schema before running shadow mode for one week.
- Do not reject unknown fields.
- Do not import SQLAlchemy models inside a schema.
- Do not write to the database from a schema.
- Do not add a schema check to a route without also removing the
  duplicated service-layer check only after the schema is fully enforcing.
- Do not coerce strings to ints/floats in the returned dict — validate only.
- Do not add `unsafe-inline` to the CSP enforce policy in order to make
  inline styles "work" — CSP and schema are unrelated concerns.

## 10. What "done" looks like

- `app/schemas/` exists, one file per domain.
- Every API route in a domain reads its payload through a schema.
- The dead `BookingSchema` import has been replaced by a real schema.
- The service layer still owns cross-field and DB-dependent checks; the
  schema owns type, presence and range.
- Every domain has a config flag.
- Shadow-mode log entries are quiet (zero rejections) for at least one
  release before enforcement.

## 11. What is deliberately out of scope of this document

- CSP policy changes.
- The geocode latency / cache workstream.
- The booking lifecycle integrity work (CONFIRMED / SEARCHING /
  request_reference).
- Any specific validator's contents. Those are written by the domain
  owner when they build the schema.

## 12. Reconciliation before enforcement

The transport `BookingSchema` (`app/schemas/transport.py`) is stricter than
the permissive service/API contract it shadows. While
`TRANSPORT_BOOKING_SCHEMA_ENFORCE` is `False` these differences are inert
(the schema only logs). They must be reconciled **before enforcement is
switched on for any surface that accepts the service/API payload shape**
(e.g. the JSON booking API), otherwise enforcement will reject requests the
service currently accepts.

For each divergence: the field, the schema behavior, the service behavior, and
the action required before enforcement.

- **`pickup_location` / `dropoff_location`** — schema requires them as strings;
  the service also accepts a structured location object. Action: accept the
  structured object in the schema too, or explicitly scope enforcement to the
  string-only web form until the API payload is reconciled.
- **`special_requirements`** — schema requires it as a string; the service also
  accepts a structured object. Action: accept the structured object in the
  schema too.
- **`accessibility_requirements`** — schema requires it as a string; the service
  also accepts a structured object. Action: accept the structured object in the
  schema too.
- **`passenger_count` / `luggage_count`** — schema requires strings; the service
  also accepts integers. Action: accept both string and integer in the schema,
  or explicitly scope enforcement to the string-only web form.
- **`luggage_count` upper bound** — schema enforces an upper bound; the service
  has no upper bound. Action: remove the upper bound from the schema, or add it
  to the service (service change requires its own review).
- **`scheduled_time`** — schema does not validate it; the service validates it
  via `validate_future_datetime`. Action: add a schema validator mirroring the
  service rule.
- **`_SOURCE_KEYS` duplication** — schema hardcodes the source keys
  (`{"gps","map","search","curated"}`); the canonical set lives in
  `app/transport/services/location_snapshot.py::VALID_SOURCES`. Action: import
  the constant rather than duplicating, or add a test asserting they stay in
  sync.

Until every divergence above is resolved (or the enforced surface is
explicitly limited to the web-form contract, which matches the schema), the
flag remains `False` and the service-layer validator
(`app/utils/validators.py::TransportValidators.validate_booking_request`)
remains the enforced path.

**Note A — pre-existing test failures.** The known-failing tests under
`tests/transport/` (booking-request points, driver console, marketplace UX,
public endpoint rate limits) are unrelated to the schema work. Baseline
proof: stashing the Phase A changes and re-running reproduces the identical
failures; the `test_driver_console` failures target a `/transport/driver-console`
route that is not defined anywhere in the codebase.

**Note B — test-logging suppression.** `migrations/env.py` calls
`logging.config.fileConfig(...)`, whose `disable_existing_loggers` default
(`True`) silently disables every pre-existing `app.*` logger for the pytest
session (see the matching `BACKLOG.md` entry). Any test asserting on `app.*`
log records must re-enable the target logger. This is recorded as its own
open decision and is independent of the schema work.
