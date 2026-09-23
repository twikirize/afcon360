# Fix 2.6 — Record (Public Endpoint Rate Limiting)

Status:          PASS (subject to human confirmation)
Date:            2026-09-23
Owner:           [your name]

Files changed:
  - app/transport/api/ride_options_routes.py   (+15 -2: limiter import, current_user import, _rate_limit_key, method_decorators)
  - app/transport/api/fare_routes.py           (+7: limiter import, shared key import, method_decorators)
  - docs/transport/fixes/Fix-2.6-contract.md   (amended §5: method_decorators + dead-decorators clarification)
  - tests/transport/test_public_endpoint_rate_limits.py   (new, 4 tests + file-local enable/reset fixture)
  - docs/transport/fixes/Fix-2.6-evidence.md   (new)

Evidence:
  See docs/transport/fixes/Fix-2.6-evidence.md

Behavior summary:
  POST /api/transport/ride-options and POST /api/transport/fare/estimate
  now enforce 30 requests per 60-second window per caller. The 31st call
  in the window returns HTTP 429 without executing the resource body.
  Calls inside the limit return the unchanged 200 success shapes.
  No other endpoint is rate-limited by this node.

Framework correction (method_decorators):
  The contract's recommended `decorators = [...]` class attribute is dead
  data under the installed flask-restful: `Resource` exposes only
  `method_decorators` (applied per request in `dispatch_request`); the
  `decorators` parameter belongs to `Api` and would have broadened scope
  to every transport resource. Both resources use `method_decorators`
  with `limiter.limit("30 per minute", ...)`. Presence check proves no
  `decorators` attribute exists on either class.

Shared _rate_limit_key note:
  Defined once in `ride_options_routes.py`, imported by `fare_routes.py`
  (no second definition, no new shared module). Resolves to
  `user:<current_user.id>` when authenticated, `ip:<request.remote_addr>`
  otherwise. Server-side limiter key only — asserted in-test, never
  rendered to responses, URLs, or templates (internal id never exposed).

Test isolation mechanism:
  Suite-wide the limiter stays disabled. This file's autouse fixture
  enables it per test (config trio + `RateLimitService.is_enabled`
  monkeypatch + one-time canonical `limiter.init_app(app)` with the
  first-request guard briefly lowered and restored + `limiter.enabled`)
  and resets the in-process memory storage before and after every test,
  restoring config itself. Other files are unaffected (proven: full
  suite green apart from 2 pre-existing failures).

30 -> 429 behavior:
  Ride (anonymous and authenticated) and fare (authenticated): 30 x 200,
  31st -> 429. Fare requires auth by design (its own 401 path untouched).

Endpoint-bucket independence:
  Exhausting ride-options leaves fare/estimate at 200 for the same caller,
  and exhausting the anonymous IP bucket leaves the authenticated caller
  at 200 on the same endpoint — scopes are per-endpoint, keys per-caller.

Runtime verification:
  Focused file: 4 passed. Full tests/transport/: 71 passed, 2 failed —
  both failures proven pre-existing via clean-tree stash check
  (test_marketplace_ux_harmonisation owner-review 302s, unrelated).

Residual risk:
  The file-local fixture briefly lowers Flask's `_got_first_request`
  guard to run the canonical `init_app` on the shared session app when
  earlier suite files already served requests; the flag is restored in
  `finally`, registration is once-only, and the per-request dynamic
  handler re-disables the limiter for all dev-config tests afterward.
  If Flask ever reads (rather than appends) setup state at request time,
  this would need revisiting — no such behavior observed.

Follow-ups:
  - The 2 pre-existing `test_marketplace_ux_harmonisation` failures (302
    vs 200 / 302 vs 403-404) are out of scope; recorded, not fixed here.
  - `bookings/show.html:295`, `drivers/location.html`,
    `vehicles/location.html` OSM hardcodes (Fix 2.4 follow-up) untouched.

Gate reference:
  Edition 2.0, Part VII, Fix 2.6
