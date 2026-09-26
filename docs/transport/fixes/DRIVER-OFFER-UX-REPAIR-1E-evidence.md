# DRIVER-OFFER-UX-REPAIR-1E — Evidence (Passenger First Name on Driver Offer Surface)

**Date:** 2026-09-26
**Gate reference:** User-provided node spec (DRIVER-OFFER-UX-REPAIR-1E), PASS
confirmed by human 2026-09-26.
**Result:** PASS (human-confirmed)

---

## 1. Scope (from the node spec)

Show the passenger's **first name only** on the driver pre-accept offer
surface (OfferService enrichment → driver-offers API → dashboard offer
card), sourced from the canonical transport passenger identity — booking
creator ≠ passenger. Visible minimum: `Passenger: John / Pickup /
Destination / Fare estimate`. Exclusions honored: no new passenger model,
no Redis storage change, no notification redesign, no wallet/KYC/migration
touch, no `phone/email/username/user_id/...` exposure (existing contract
test's forbidden-field list untouched and green).

## 2. Files changed

```text
app/transport/services/offer_service.py | 97 ++++++++++++++++++++++++++++++--
1 file changed, 93 insertions(+), 4 deletions(-)
```

```text
?? tests/transport/test_driver_offer_passenger_first_name.py
```

`templates/transport/driver/driver_dashboard.html` — exactly 4
passenger-only insertions (verified via `git diff`, hunks isolated below);
the same file carries a concurrent actor's workspace-consolidation hunks
(title/currency/`All trips` panel/`data-url` reference-keying), NOT this
node's work:

```text
+ {% set o0_pax = (o0.get('passenger') or {}) %}
+ {% if o0_pax.get('first_name') %}<span>Passenger: {{ o0_pax.get('first_name') }}</span><span>·</span>{% endif %}
+ {% set o_pax = (o.get('passenger') or {}) %}
+ {% if o_pax.get('first_name') %}Passenger: {{ o_pax.get('first_name') }} · {% endif %}
```

## 3. Implementation

- `enrich_offer` (`offer_service.py`) computes
  `passenger_first_name = cls._passenger_first_name_or_none(booking, ref)`
  and emits `detail["passenger"] = {"first_name": ...}` only when truthy;
  any failure omits the key and logs a warning (1D/1C-6 failure-class
  pattern — the offer itself never fails).
- `_passenger_first_name_or_none`: canonical row first
  (`passenger_service.passengers_for_booking(booking_id)` — created_at
  asc, soft-delete excluded, cancelled excluded): row `name` token →
  linked `passenger.user` display token → None; no rows (self-booking,
  which writes no passenger row) → `booking.user.display_name` token;
  whole body try/except → warning + None.
- `_first_name_token`: first whitespace token, `@`-shaped tokens rejected
  (email-ish values yield omission, never a leak).
- Docstring updated: `passenger {first_name}` field listed; "deliberately
  absent" paragraph narrowed; failure handling documents omission.
- Dashboard focus card and list card render `Passenger: <first>` first in
  the metadata row when the key exists; absent key renders the pre-1E
  layout unchanged.

## 4. Verification

Focused suite (`tests/transport/test_driver_offer_passenger_first_name.py`,
8 tests):

```text
first run: 6 failed, 2 passed  →  root cause: add_passenger() only flushes;
test helper now commits (db.session.commit() after the service call).
second run: 8 passed (239.46s)
```

Failures were fixed at the test's own root cause, not masked; the product
code was unchanged to make them pass.

Regression batch (contract + first-name + concurrent-claim +
workspace-sections + driver-console + driver-dashboard):

```text
12 failed, 70 passed, 37 warnings in 134.67s
```

All 12 failures proven NOT this node's (evidence):
- `tests/transport/test_driver_console.py` x4 — 404s: the `driver-console`
  route does not exist in current code (grep: zero matches in
  `app/transport/routes.py` + `app/transport/api/driver_routes.py`); user
  confirmed "we no longer have driver-console" — stale tests for the
  concurrent actor's route removal.
- `tests/test_driver_workspace_sections.py` x8 — sections
  (Active Trip / Performance / Scheduled / Recent Trips / Vehicle
  Switching / Safety / Online Toggle) rewritten by the concurrent actor's
  uncommitted workspace consolidation (`base.html`, `driver_routes.py`,
  `driver-dashboard.css`, and partial test edits visible in `git diff`);
  regions this node's 4 template insertions never touch.
- Offer-related suites all green: `test_driver_offer_contract.py`
  (other actor's file, run unmodified — including its
  `forbidden_fields_absent` PII/ID list), `test_driver_offer_passenger_first_name.py`,
  offer sections of `test_driver_workspace_sections.py`,
  `test_transport_concurrent_claim.py`, `test_transport_driver_dashboard.py`.

```text
python -c "from app import create_app" → APP_IMPORT_OK, exit 0
```

## 5. Privacy proof

New tests assert: passenger object contains exactly `{"first_name"}`;
serialized blob contains no `phone/email/username/user_id/passenger_details/
Creator/Traveller` substrings and no `driver_id/vehicle_id/user_id/
passenger_id/booking_id` keys; nameless email-only passenger → key omitted
with pickup/fare intact.

## 6. Environment / process

- No migration, no Redis change, no commit. Register is the human's step.
- Concurrent worktree (workspace consolidation, console removal,
  `notification_service.py`, `test_driver_offer_contract.py` by other
  actors) read-only for this node.
- LSP SQLAlchemy/pylance diagnostics treated as pre-existing noise per
  standing rule.
