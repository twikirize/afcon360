# Fix Contract — Fix 2.6 — Public Endpoint Rate Limiting

**Owner:** [your name]
**Date:** 2026-09-23
**Status:** READY FOR AGENT
**Roadmap reference:** Edition 2.0, Part VII, Fix 2.6
**Report format:** Compact

---

## 1. Guarantee

The two public, anonymous-allowed endpoints

    POST /api/transport/ride-options
    POST /api/transport/fare/estimate

enforce a per-caller limit of 30 requests per 60-second window.
Exceeding the limit returns HTTP 429 without executing the resource
body. The limit is keyed by the authenticated user's id when a
session exists, and by the caller's IP address otherwise. No other
endpoint is rate-limited by this node.

## 2. Current Behavior

Both resources accept unlimited requests. No rate limiting is
applied.

Verified by reading:
- `app/transport/api/ride_options_routes.py::RideOptionsResource.post`
  — no decorator, no limiter call.
- `app/transport/api/fare_routes.py::FareEstimateResource.post`
  — no decorator, no limiter call.
- `app/transport/decorator.py::rate_limit` — this decorator exists
  but is a **no-op stub**: its body simply calls `f(*args, **kwargs)`
  without any counting or Redis check. Adding `@rate_limit(...)` to a
  resource would not enforce anything.
- `app/extensions.py` — Flask-Limiter (`limiter`) is initialized for
  the app. It is the canonical rate-limiting mechanism.

## 3. Scope — Files In

- `app/transport/api/ride_options_routes.py`
  → apply a real per-caller limit to `RideOptionsResource.post`.

- `app/transport/api/fare_routes.py`
  → apply the same limit to `FareEstimateResource.post`.

- `tests/transport/test_public_endpoint_rate_limits.py`
  → new file, tests named in Section 6.

## 4. Scope — Files Out

- `app/transport/decorator.py` — the `rate_limit` decorator is a
  no-op stub. Making it real would silently rate-limit **every**
  route that already carries it, which is out of scope for this
  node. Do NOT modify this file.
- `app/extensions.py` — `limiter` is already initialized. No change.
- `app/config.py` — no config key is added by this node.
- `app/transport/api/routes.py` — resource registration is unchanged.
- `app/__init__.py` — do not touch the limiter enable/disable logic.
- `app/transport/api/booking_routes.py`, `driver_routes.py`,
  `reservation_routes.py`, `vehicle_routes.py`,
  `organisation_routes.py`, `route_routes.py`, `incident_routes.py`,
  `analytic_routes.py`, `dashboard_routes.py`, `settings_routes.py`
  — not in scope.
- `tests/conftest.py`
- `requirements.txt`
- Any migration
- Any template
- Any file not listed in Section 3.

## 5. Interface Contract

### Mechanism

Use Flask-Limiter directly. Do NOT use the no-op
`app.transport.decorator.rate_limit`.

Attach the limit at the resource class level so every method of the
resource inherits it. The required form is:

```python
from app.extensions import limiter

class RideOptionsResource(Resource):
    method_decorators = [
        limiter.limit("30 per minute", key_func=_rate_limit_key),
    ]

    def post(self):
        ...
```
with the same shape applied to FareEstimateResource.

The flask-restful Resource hook is `method_decorators`, not `decorators`. The class-level `decorators` attribute is dead data — no wrapper runs.

Key function
Define a single key function used by both resources. It must
resolve to:

- `user:<current_user.id>` when `current_user.is_authenticated`
  is True

- `ip:<request.remote_addr>` when the caller is anonymous

The key function may live in either of the two in-scope resource
files, or in a small shared module placed inside `app/transport/`
if the agent traces a genuine need for sharing. It must not be
added to `app/transport/decorator.py`.

Response on limit exceeded
HTTP 429. The existing response contract for a successful call
(200 with the ride-options or fare-estimate JSON shape) is
unchanged for calls inside the limit.

Do not modify the 400/401/403/404/500 handlers. Only the 429 path
is new.

Anonymous endpoints
RideOptionsResource.post and FareEstimateResource.post are
anonymous-allowed. The limit applies to anonymous callers via IP.

## 6. Proof of Done

### Command 1

    pytest tests/transport/test_public_endpoint_rate_limits.py -v

Expected: 4 tests pass.

- `test_ride_options_allows_under_limit` — 30 sequential calls
  return 200
- `test_ride_options_returns_429_at_limit` — call 31 returns 429
- `test_fare_estimate_returns_429_at_limit` — same for the fare
  endpoint
- `test_anonymous_calls_are_limited_by_ip` — anonymous caller hits
  the limit and receives 429

Each test must reset the limiter storage before running, so tests
do not interfere with each other or with the rest of the suite.

### Command 2

    pytest tests/transport/ -v

Expected: all transport tests still pass. No regression in
test_tile_provider_config.py or any other transport test.

### Command 3

    python -c "from app import create_app; a=create_app();
    print('limiter present:', 'limiter' in a.extensions or hasattr(a, 'extensions'))"

Expected: limiter present: True. This confirms Flask-Limiter is
initialized in the app; if it is not, the node is BLOCKED.

### Command 4 — targeted git proof

    git diff --stat -- app/transport/decorator.py

Expected: no output. The stub decorator file must not be touched.

    git diff --stat -- app/transport/api/ride_options_routes.py
        app/transport/api/fare_routes.py

Expected: only the two files listed. (Note: fix24 — see below.)

    git status --short -- tests/transport/test_public_endpoint_rate_limits.py

Expected: ?? (new, untracked).

## 7. Rollback

    git revert <commit-sha-of-this-node>

No migration. No schema. No data. Rollback time under 30 seconds.
The limiter's Redis keys expire on their own.

## 8. Constraints (Do NOT)

- Do NOT modify `app/transport/decorator.py`. The stub stays a stub.
- Do NOT modify `app/extensions.py` or `app/__init__.py`.
- Do NOT introduce a new dependency. Flask-Limiter is already
  installed and initialized.
- Do NOT modify any other API resource.
- Do NOT add a config key.
- Do NOT modify `tests/conftest.py` or any shared fixture. If the
  tests need per-test limiter reset, do it inside the new test file.
- Do NOT modify the success-path response shape of either endpoint.
- Do NOT change the HTTP methods, auth requirements, or input
  schemas of either endpoint.
- Do NOT commit. Propose and stop.
- Do NOT run `flask db migrate` or `flask db upgrade`.

## 9. Acceptance Criteria

- [ ] `RideOptionsResource.post` enforces 30 req / 60 s per caller.
- [ ] `FareEstimateResource.post` enforces 30 req / 60 s per caller.
- [ ] Limit is keyed by user id when authenticated.
- [ ] Limit is keyed by IP when anonymous.
- [ ] HTTP 429 is returned on the 31st call in the window.
- [ ] Successful-path response shape unchanged.
- [ ] 4 tests pass.
- [ ] Full `tests/transport/` suite still passes.
- [ ] `app/transport/decorator.py` has no diff.
- [ ] No new dependency.
- [ ] No migration in the diff.
- [ ] No config key added.

## Notes for the Agent

Before proposing a plan, read:

- `app/transport/api/ride_options_routes.py`
- `app/transport/api/fare_routes.py`
- `app/transport/decorator.py` (to confirm the stub is a no-op)
- `app/extensions.py` (to confirm limiter is present and how it
  is initialized)
- `app/__init__.py` around the limiter enable/disable logic

Answer these two questions in your plan:

1. Is Flask-Limiter enabled or disabled in the current test
   configuration? If disabled, how does the test enable it for
   its own execution without touching `app/config.py`,
   `app/__init__.py`, or `tests/conftest.py`?

2. What is the correct way to reset the limiter between tests so
   that the 30-per-minute counter from one test does not leak into
   the next?

Do not write code until the human approves your plan.