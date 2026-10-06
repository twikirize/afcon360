# SUPPLY-LOCK-SITE-1048 — Evidence

Node: SUPPLY-LOCK-SITE-1048
Phase: IMPLEMENTATION (follow-up run after APPROVED ConflictError kwargs fix)
Date: 2026-10-02
Status at write time: CLOSED — VERIFIED (control session sign-off received)

Human contract: implementation authorization SUPPLY-LOCK-SITE-1048
(APPROVED — EXPAND TO A + B + C), plus follow-up APPROVE of the
duplicate-branch ConflictError kwargs correction with the
details={"organisation_id": ...} refinement.

---

## 1. Pre-flight results (read-only, before any edit)

### §0.1 — DB duplicate guarantee: PASS
`Select-String app/transport/models.py -Pattern organisation_id`:
- Line 527: `Index("ix_org_profile_org_id", "organisation_id", unique=True)`
- Line 552: `organisation_id = db.Column(db.BigInteger, db.ForeignKey("organisations.id"), nullable=False, unique=True)`
DB is authoritative; no SUPPLY-ORG-DUP-UNIQUE filing required.

### §0.2 — Fixtures
`tests/conftest.py`: `test_user`, `test_admin`, `admin_client`, `authenticated_client` exist.
`tests/test_transport_concurrent_claim.py`: `_create_user`, `_create_driver`,
`_create_vehicle`, `_create_booking`, `_delete` exist. No Organisation helper
exists anywhere (repo-wide `Select-String "Organisation\(" tests` hit only the
new test file) → minimal local helpers written in the new test file.

### §0.3 — Registry stub: MISSING
`Test-Path app/organisation/services/registry_service.py` → False.
`Get-ChildItem app -Directory` → no `organisation` directory (only
`app/identity/models/organisation.py`). `get_organisation_identity`
fail-closes with ServiceUnavailableError → test injects a fake
`app.organisation.services.registry_service` module via
`monkeypatch.setitem(sys.modules, …)`, documented in the test file header.

### §0.4 — Rate limiter
`app/utils/rate_limiting.py`: in-memory `RateLimiter` + `_rate_limit_store`
(no Redis). TestingConfig sets `RATELIMIT_ENABLED = False` (Flask-Limiter,
separate mechanism). Test clears the in-memory store before each call and
scopes the Redis mock to the redis client only.

### §0.5 — Email validator domain (live probe)
`.venv\Scripts\python.exe -c "from app.utils.validators import TransportValidators as T; ..."`:
- `T.validate_email('ops@afcon360.com')` → `(False, 'The domain name afcon360.com does not exist.')`
- `T.validate_email('ops@gmail.com')` → `(True, '')`
- `T.validate_phone('+256700111222')` → `(True, '')`
- `'KE' in T.AFCON_COUNTRIES` → True
Payload uses `@gmail.com`.

Baseline `git status --porcelain` (before edits): `M "fine tuning transport.md"` only (pre-existing).

---

## 2. Production diff (exact)

`git diff -- app/transport/services/provider_service.py`:

```diff
@@ -1062,19 +1062,27 @@ class ProviderService:
             # Verify organisation eligibility
             eligibility = self.validate_organisation_eligibility(organisation_id)

-            # Validate transport data
-            sanitized_data = sanitize_input(data)
-            validation_result = validate_organisation_transport(sanitized_data)
+            # Validate transport data. ``sanitize_input`` operates on strings
+            # only; sanitize each string value of the mapping (same pattern
+            # as register_driver / register_vehicle_internal).
+            sanitized_data = {
+                key: sanitize_input(value) if isinstance(value, str) else value
+                for key, value in (data or {}).items()
+            }
+            # validate_organisation_transport returns Tuple[bool, List[str]].
+            is_valid, validation_errors = validate_organisation_transport(sanitized_data)

-            if not validation_result['valid']:
+            if not is_valid:
                 raise ValidationError(
                     message="Organisation transport validation failed",
-                    details=validation_result['errors'],
+                    details=validation_errors,
                     code="VALIDATION_FAILED"
                 )

-            # Check for existing registration
-            with with_cache_lock(f"lock:org_transport:{organisation_id}", timeout=10):
+            # Check for existing registration. with_cache_lock is a decorator
+            # factory, not a context manager; _redis_lock is the module-local
+            # context-manager equivalent already proven at site 667.
+            with _redis_lock(f"lock:org_transport:{organisation_id}", ttl=10):
                 existing = OrganisationTransportProfile.query.filter_by(
                     organisation_id=organisation_id,
                     is_deleted=False
@@ -1083,9 +1091,10 @@ class ProviderService:
                 if existing:
                     raise ConflictError(
                         message="Organisation already registered for transport",
-                        resource_type="organisation_transport",
-                        resource_id=organisation_id,
-                        code="ALREADY_REGISTERED"
+                        resource="organisation_transport",
+                        conflict_type="ALREADY_REGISTERED",
+                        code="ALREADY_REGISTERED",
+                        details={"organisation_id": organisation_id},
                     )
```

Hunks 1–3 = authorized A+B+C. Hunk 4 = control-session-APPROVED
ConflictError kwargs correction (org branch only; `register_driver`
branch ~line 705 untouched — LSP still flags it, by design).

Module import check: `python -c "from app.transport.services.provider_service
import ProviderService"` → `import OK`.

---

## 3. Test runs (raw outcomes)

### 3.1 New regression file — BEFORE kwargs fix
`pytest tests/transport/test_org_registration_lock.py -v` →
1 passed, 2 failed. Both failures:
`TypeError: ConflictError.__init__() got an unexpected keyword argument
'resource_type'` at `provider_service.py:1092` (duplicate branch).
Test 1 (real path) passed; test 3 first assertion (Redis down → success)
passed. Work stopped per "stop and report" clause → BLOCKED report filed.

### 3.2 New regression file — AFTER approved fix
`pytest tests/transport/test_org_registration_lock.py -v` →
**3 passed** (17.32s):
- test_org_registration_path_completes PASSED
- test_org_registration_duplicate_prevented PASSED
- test_org_registration_survives_redis_failure PASSED

### 3.3 Adjacent: `pytest tests/transport/test_supply00_override.py -q`
**16 passed** (unchanged across both runs).

### 3.4 Adjacent: `pytest tests/test_transport_concurrent_claim.py -q`
Run 1 (pre-fix session): 26 passed / 3 failed
(`test_late_release_does_not_free_reclaimed_resources`,
`test_offline_driver_release_keeps_unavailable`,
`test_offline_driver_cancel_post_assignment_stays_unavailable`).
Run 2 (post-fix session): 25 passed / 4 failed — same 3 plus
`test_one_driver_two_bookings`, which failed on
`psycopg2.errors.DeadlockDetected` between two racing
`SELECT … FOR UPDATE` threads in `AssignmentService.claim`
(unhandled thread exception → `losses == 0`, expected 1).
That file references `register_organisation_transport`/`ProviderService`
zero times (grep count 0); failure set varies run-to-run with no code
change between runs → pre-existing flake, Agent 2's SUPPLY-00-TEST-UPDATE lane.

---

## 4. Grep / status proofs

- `with_cache_lock` in provider_service.py: import line 54 + comment lines
  69–70, 1082 only. No `with with_cache_lock(...)` usage remains.
- `_redis_lock` in provider_service.py: definition line 66, driver site 696,
  org site 1085.
- `git status --porcelain -- migrations/` → empty (no migrations).
- Final `git status --porcelain`:
  `M app/transport/services/provider_service.py`,
  `?? tests/transport/test_org_registration_lock.py`,
  plus pre-existing `M "fine tuning transport.md"` and parallel-session
  `?? docs/transport/nodes/SUPPLY-ELIGIBILITY-v1.md` (both untouched).

## 5. Registry-absence proof (SUPPLY-ORG-REGISTRY-PACKAGE, P1)

- No `app/organisation` directory; no `registry_service.py` anywhere;
  no `def get_organisation` anywhere in `app/`.
- Sole repo reference: `provider_service.py:250`
  (`from app.organisation.services.registry_service import OrganisationRegistry`).
- No route/caller references `register_organisation_transport` or
  `validate_organisation_eligibility` outside the service itself.
- Consequence: every production call fail-closes with
  ServiceUnavailableError at eligibility — feature non-functional in prod.

## 6. Scope interpretation (Condition 1, verbatim)

"The authorized phrase 'protected check/insert logic' was interpreted to
govern the decision flow (query → if-found → refuse; else insert), not the
exception kwargs by which the refusal is communicated. The check and insert
are unchanged; only the raise is corrected."

## 7. Follow-ups filed

- SUPPLY-DRIVER-CONFLICT-KWARGS (P1, OPEN) — identical kwargs bug in
  `register_driver` (~line 705). Separate node.
- SUPPLY-ORG-REGISTRY-PACKAGE (P1, OPEN) — §5 above. Separate node.
- SUPPLY-00-TEST-UPDATE (P1, existing, Agent 2's lane) — §3.4 failures.
