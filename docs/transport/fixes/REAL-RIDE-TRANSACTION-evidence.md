# REAL RIDE TRANSACTION — Evidence (SELECT → BOOK → OFFER → ASSIGNMENT)

Status:          PASS (transaction path proven; browser booking blocked
                 by auth/supply, honestly reported)
Date:            2026-09-23

## Data-flow map (all verified in current code)

Browser ride-options → POST /api/transport/ride-options (anonymous,
rate-limited) → live per-class availability (available_by_class) +
canonical fare engine → options[] with vehicle_class/fare/ETA.
Select → POST /transport/book (auth + profile + KYC2 + 5/min) →
BookingSchema-or-raw → validate_booking_request (vehicle_class
whitelisted against VehicleClass) → BookingService.create_booking →
service_subtype + booking_metadata.vehicle_class + server fare +
distance basis → PENDING_PAYMENT → redirect bookings_show.
Dispatch (recovery beat): MatchingService.discover_and_offer →
class-aware pool (vehicle_classes.contains) + ranker (fresh ≤300s
canonical location required, +25 class match, ≥40 threshold) →
OfferService.create_offer (Redis, TTL) → driver GET offers →
POST accept → Lua CAS → AssignmentService.claim (exclusive) →
ASSIGNED + assigned_driver_id/vehicle_id.

## Vehicle-class proof

Server-authoritative: validator whitelist; persisted to
service_subtype + metadata; fare computed per class server-side;
matching pool-filters + scores on it. JS selection never trusted
for fare/auth. No defect: enforced, not a future feature.

## Browser evidence (live server, real page)

- GET /transport/ → 200. Map ready ("Distance is a straight-line
  estimate until a routing service is connected").
- Pickup "Kampala Road, Kampala" + destination "Mandela National
  Stadium, Namboole" entered; Find a Ride → POST ride-options → 200:
  success:true, options:[], note = live-availability wording,
  distance_basis planning_default (typed addresses carry no coords).
- Empty is honest: ranker requires fresh driver locations; dev
  drivers (6 online+available, 4 with vehicle) have none fresh.
  No locations fabricated, no supply invented.
- Booking in-browser blocked: requires login + KYC tier 2 (no
  credentials fabricated). Steps 7–12 proven via sanctioned tests.

## Test evidence (exact)

- test_transport_booking_route_path.py: route POST → booking row
  (subtype/metadata comfort, straight_line_planner, fare) →
  discover_and_offer (≥1) → accept → claim → ASSIGNED + ids. PASS.
- concurrent_claim + d2_evidence + d5 + moderator + integrity +
  fare_engine/governance + front_page + rate_limits +
  booking_request_points + d3: all green except two reconciled items:
  (1) d2 fare-label test was stale vs intentional Fix-2.3 rename
  ("Estimated Fare" → "Base fare" payment breakdown; value still
  base_price) — assertion updated with reason, now green;
  (2) front-page retired-URL test expects 301 but the security gate
  redirects first (302 login/home) — pre-existing, recorded as BL-27,
  untouched (gate change needs owner call).
- distance_basis unchanged (straight_line_planner / planning_default
  where legitimate). No Valhalla, fare, wallet, migration changes.

## Fixes made

- tests/test_transport_d2_evidence.py: stale fare-label assertion
  updated (proven: intentional Fix-2.3 restructure).

## Deferred / backlog

- BL-27 (new): stale front-page test vs gate on retired URL.
- BL-24 signal emission gap stands (producers: recovery beat for
  offers; driver signal still unwired — unchanged).

Gate: SELECT→BOOK PASS, BOOK→OFFER PASS, OFFER→ASSIGNMENT BLOCKED →
REAL RIDE TRANSACTION NODE: BLOCKED (corrected 2026-09-23,
DIAGNOSE-FRESH-LOCATION-GAP: code path test-proven, live consumer
path blocked — legitimate supply exists but no driver has a fresh
≤300s location, so no real offer reaches the live rider path; see
docs/transport/fixes/DIAGNOSE-FRESH-LOCATION-GAP-record.md). No
supply, location, offer, or assignment was fabricated.
