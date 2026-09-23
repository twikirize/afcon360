# Fix 2.6 — Evidence (Public Endpoint Rate Limiting)

**Date:** 2026-09-23
**Owner:** [your name]
**Gate reference:** Edition 2.0, Part VII, Fix 2.6
**Result:** PASS (subject to human confirmation)

---

## 1. Contract amendment (Step 1)

`docs/transport/fixes/Fix-2.6-contract.md` §5 Mechanism amended:
`decorators` -> `method_decorators`, plus the one-line clarification:

> The flask-restful Resource hook is `method_decorators`, not `decorators`. The class-level `decorators` attribute is dead data — no wrapper runs.

`git diff -- docs/transport/fixes/Fix-2.6-contract.md` output: empty —
expected, the contract file is new and untracked:

```text
?? docs/transport/fixes/Fix-2.6-contract.md
```

## 2. RideOptions diff (Step 2)

`git diff -- app/transport/api/ride_options_routes.py`:

```diff
diff --git a/app/transport/api/ride_options_routes.py b/app/transport/api/ride_options_routes.py
index 04f8c11..cefb378 100644
--- a/app/transport/api/ride_options_routes.py
+++ b/app/transport/api/ride_options_routes.py
@@ -10,8 +10,10 @@ invents availability, price, or distance.
 import logging

 from flask import request
+from flask_login import current_user
 from flask_restful import Resource

+from app.extensions import limiter
 from app.transport.models import Currency, VehicleClass
 from app.transport.services import fare_service
 from app.transport.services.availability_service import (
@@ -31,6 +33,17 @@ _DISPLAY_NAMES = {
 }


+def _rate_limit_key():
+    """Per-caller rate-limit key shared by the public estimate endpoints.
+
+    Authenticated callers are keyed by user id; anonymous callers by IP.
+    Server-side limiter key only — never rendered or exposed.
+    """
+    if current_user.is_authenticated:
+        return f"user:{current_user.id}"
+    return f"ip:{request.remote_addr}"
+
+
 class RideOptionsResource(Resource):
     """POST /api/transport/ride-options

@@ -39,6 +52,10 @@ class RideOptionsResource(Resource):
     KYC + rate limit unchanged).
     """

+    method_decorators = [
+        limiter.limit("30 per minute", key_func=_rate_limit_key),
+    ]
+
     def post(self):
         data = request.get_json(silent=True) or {}
         service_type = data.get("service_type") or "on_demand"
```

Step 2 gate: diff contains only the limiter import (+ `current_user`
import required by the key function), the `_rate_limit_key` definition,
and `method_decorators`. PASS.

## 3. Fare diff (Step 3)

`git diff -- app/transport/api/fare_routes.py`:

```diff
diff --git a/app/transport/api/fare_routes.py b/app/transport/api/fare_routes.py
index bbd19d1..0e759a8 100644
--- a/app/transport/api/fare_routes.py
+++ b/app/transport/api/fare_routes.py
@@ -22,12 +22,19 @@ import logging
 from flask import request
 from flask_restful import Resource

+from app.extensions import limiter
+from app.transport.api.ride_options_routes import _rate_limit_key
+
 logger = logging.getLogger(__name__)


 class FareEstimateResource(Resource):
     """POST /api/transport/fare/estimate"""

+    method_decorators = [
+        limiter.limit("30 per minute", key_func=_rate_limit_key),
+    ]
+
     # NOTE: no @login_required decorator here on purpose (see below).
     def post(self):
         from flask_login import current_user
```

Step 3 gate: only the limiter import, the shared key import, and
`method_decorators`. No second key function. PASS.

## 4. Fare 200 probe (Step 4)

Temporary probe file `tests/transport/test_fix26_probe_tmp.py` (deleted
after the run; `Test-Path` returned `False`), using existing fixtures,
no seeding, no conftest change:

```text
FARE-PROBE status=200 body={
    "success": true,
    "data": {
        "currency": "USD",
        "currency_note": "Amounts follow the base fare tables; no FX conversion is performed.",
        "version": 1,
        "total": 35.1,
        ...
        "distance_basis": "planning_default",
        ...
    }
}
PASSED
RIDE-PROBE status=200 body={
    "success": true,
    "data": {
        "service_type": "on_demand",
        "currency": "USD",
        "distance_km": null,
        "distance_basis": "planning_default",
        "options": [],
        ...
    }
}
PASSED
2 passed, 4 warnings in 11.75s
```

Probe returned 200 for both endpoints — no HARD STOP. Continued.

## 5. Focused 4-test result (Step 6)

`.venv\Scripts\python.exe -m pytest tests/transport/test_public_endpoint_rate_limits.py -v`:

```text
test_ride_options_allows_under_limit PASSED [ 25%]
test_ride_options_returns_429_at_limit PASSED [ 50%]
test_fare_estimate_returns_429_at_limit PASSED [ 75%]
test_anonymous_calls_are_limited_by_ip PASSED [100%]
4 passed, 4 warnings in 25.48s
```

Note: first attempt at the anonymous key unit assertion failed
(`ip:None` — bare `test_request_context` supplies no REMOTE_ADDR).
Fixed inside the test file with
`environ_overrides={"REMOTE_ADDR": "127.0.0.1"}`; implementation
unchanged. Also fixed one LSP notice (`resp = None` init) the same way.

## 6. Full transport suite (Step 7)

`.venv\Scripts\python.exe -m pytest tests/transport/ -v`:

```text
2 failed, 71 passed in 128.77s (0:02:08)
```

Failures (both in `test_marketplace_ux_harmonisation.py`, both run
BEFORE this node's tests alphabetically, both unrelated HTML/owner
review-page flows):

```text
FAILED test_owner_review_page_access_and_flow — assert 302 == 200
FAILED test_unauthorized_owner_cannot_view_review_page — assert 302 in (403, 404)
```

Pre-existing proof: stashed this node's two tracked edits, moved this
node's test file out, re-ran exactly those two tests on the clean tree:

```text
2 failed in 24.06s
```

Same 2 failures without Fix 2.6. Stash popped, test file restored,
`git status` verified (`M` on the two resource files, `??` on the new
test + contract). All 4 Fix 2.6 tests pass in-suite.

Process note: the first full-suite run errored this node's 4 tests at
fixture setup — `limiter.init_app(app)` calls `app.before_request`,
which Flask forbids after the first request (earlier suite files run
first on the shared session app). Fixed inside the test file only: the
fixture calls the canonical `init_app` once, guarded by
`app.extensions`, lowering `app._got_first_request` solely for that
call and restoring it in `finally`. Verified by running an earlier
suite file plus this file together: `6 passed`.

## 7. Limiter presence check (Step 8)

Contract command + resource-level proof (temp script, deleted after):

```text
limiter present: True
RideOptionsResource method_decorators: [('RouteLimit', '30 per minute')]
FareEstimateResource method_decorators: [('RouteLimit', '30 per minute')]
key func shared: True
FareConfigResource limited: False
BookingListResource limited: False
dead 'decorators' attr present: (False, False)
stub untouched: True
```

Limiter is on exactly the two contracted resources, not global, not via
the dead attribute, stub file untouched.

## 8. Targeted git proof (Step 9)

`git diff --stat -- app/transport/decorator.py` → no output (untouched).

```text
 app/transport/api/fare_routes.py         |  7 +++++++
 app/transport/api/ride_options_routes.py | 17 +++++++++++++++++
 2 files changed, 24 insertions(+)
```

`git status --short -- tests/transport/test_public_endpoint_rate_limits.py`:

```text
?? tests/transport/test_public_endpoint_rate_limits.py
```

Remaining working-tree entries (`BACKLOG.md`, `app/auth/helpers.py`,
`app/config.py`, `app/notifications/services.py`,
`app/transport/routes.py`, `app/utils/module_guard.py`,
`templates/transport/bookings/index.html`, `home.html`,
`new_home.html`, T-10 docs, My Trips tests, Fix 2.4 files) are
pre-existing concurrent work, explicitly NOT Fix 2.6.

## 9. Environment / config state

- Date 2026-09-23, Windows, Python 3.13.14, Flask-Limiter 4.0.0.
- Suite runs with the limiter disabled (`TestingConfig.RATELIMIT_ENABLED=False`,
  dev disable handler); this node's test file enables it per-test via its
  own fixture (config + `RateLimitService.is_enabled` monkeypatch +
  one-time canonical `init_app` + `limiter.reset()`), self-restoring.
- Storage: in-process `memory://`; no Redis involved.
- No migration, no config key, no new dependency, no commit, no register update.
