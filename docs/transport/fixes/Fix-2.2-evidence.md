# Fix 2.2 — Evidence

Node: Fix 2.2 (EGGE implementation node, roadmap Edition 2.0)
Contract: `docs/transport/fixes/Fix-2.2-contract.md` (all six decisions RESOLVED — 2026-09-23)
Date: 2026-09-23
Scope: Redis-backed circuit breakers on the directions path,
`app/transport/services/external_platforms.py` + `tests/transport/test_directions_circuit_breaker.py`.

## 1. Technical discovery (pre-implementation inspection)

- **No existing Redis circuit:** no `transport:circuit:*` keys, no Redis breaker on any
  directions path. The only breaker-like utility, `with_circuit_breaker` in
  `app/utils/monitoring.py`, is a process-local decorator unused by the directions
  path — left **untouched** (verified: `git diff --stat -- app/utils/monitoring.py`
  empty throughout).
- **Existing broad exception swallowing:** `get_directions` caught bare `Exception`
  and re-raised `ServiceUnavailableError`, which would have bypassed any inner
  circuit observation (failure → mock without counting).
- **Provider-neutral outcome model:** dispatch on the strings `google` / `mapbox`;
  circuit identity = (provider, operation=`directions`).
- **Zero-current-caller finding (D-Dormancy):** no production caller of the
  directions circuit path exists; per contract, no caller was added. Dormancy is
  an evidence note, not a defect.
- **`_mock_directions` preservation:** body and output shape byte-identical;
  verified by T9 shape test (passing) and by diff review (no hunk touches the
  mock body; only Step-2 fallback-handler narrowing references it).

## 2. Implementation (authorized)

`app/transport/services/external_platforms.py` (Step 2; diff vs HEAD 226+/77−, then
one correction hunk):

- Constants `CIRCUIT_FAILURE_THRESHOLD=5`, `CIRCUIT_RECOVERY_TIMEOUT=30`,
  `CIRCUIT_FAILURE_TTL=60`, `CIRCUIT_OPERATION="directions"`.
- `CircuitOpenError`; `PROVIDER_FAILURE_EXCEPTIONS` (ConnectionError/Timeout/HTTPError);
  `DIRECTIONS_FALLBACK_EXCEPTIONS`.
- Helpers `_circuit_keys` (exactly the two approved keys), `_as_int` (bytes-safe),
  `_circuit_state`, `_record_failure` (INCR==5 ⇒ SET state open EX 30 + log +
  `record_metric`), `_record_success` (DEL failures), `circuit_breaker(provider)`.
- Split legs `_google_directions_call` / `_mapbox_directions_call` (decorated);
  outer `get_directions` narrows to `except DIRECTIONS_FALLBACK_EXCEPTIONS` → mock.
  Config check runs before the decorator (CONFIGURATION_UNAVAILABLE: no HTTP,
  uncounted, no reset). Provider-declared error/status ⇒ HTTPError ⇒ counted.
  Parser-shape errors (`KeyError`/`TypeError`/`IndexError`) ⇒ LOCAL_DEFECT, escape.
- Recovery: state-absent ∧ failures≥5 ⇒ atomic-DEL claim; claimant logs
  `reason=recovery_expired`; all observers resume CLOSED.

## 3. Concurrency discovery (T12)

- **Before correction:** deterministic two-worker rendezvous test produced
  `assert 2 == 1` — two identical `recovery_expired` emissions. Root cause: the
  log was emitted from a non-atomic read observation before the reset delete.
- **Minimal correction:** emission gated on the atomic `DEL` result
  (`claimed = redis_client.delete(failures_key); if claimed: log`).
  Same two keys; no lock, no HALF-OPEN, no probe, no third key.
- **After correction:** T12 passes — exactly 1 recovery log, 2 successful resumed
  provider calls, post-claim state absent / failures 0.

## 4. Scope-gap (process deviation, recorded for audit)

- **Original step:** focused test verification.
- **Observed defect:** existing recovery transition not concurrency-safe.
- **Evidence:** pre-fix T12 reproduced 2 recovery logs from concurrent
  first-after-expiry observers.
- **Correction:** atomic DEL claim gates recovery-transition emission.
- **Authorization status:** production edit occurred within the verification step
  rather than after a separately stated production-edit authorization.
- **Disposition:** accepted — the change was required by the approved contract
  (single recovery transition, contract:238-240, 260), minimal (one hunk),
  directly evidenced (failing-then-passing T12), and verified (16/16 + full
  suite classified). Deviation recorded here for transparency; not normalized
  as pre-authorized.

## 5. Contract interpretation (final, authoritative)

- **CLOSED→OPEN:** transition log (`provider`, `operation`, `failure_count`,
  `reason=threshold_reached`) **+ `record_metric("circuit.open.<provider>.directions", 5)`** (contract:259).
- **OPEN→CLOSED:** transition log (`provider`, `operation`, `reason=recovery_expired`
  + failure-count evidence) — **log only; no recovery transition metric required
  in Fix 2.2** (contract:260). No production change was made to add one.

## 6. Verification commands + outcomes

| # | Command | Outcome |
|---|---------|---------|
| 1 | `py_compile` on both Fix 2.2 files + `python -c "from app import create_app"` | `IMPORT_OK` (Step 2) |
| 2 | `pytest tests/transport/test_directions_circuit_breaker.py -v` | **16 collected, 16 passed, 0 failed** (T1–T11 incl. T4×3 = 15, + T12) |
| 3 | New T12 vs unfixed production | **FAILED `assert 2 == 1`** (gap proven), then **PASSED** post-fix |
| 4 | `pytest tests/transport/ -v` | **105 collected: 103 passed, 2 failed**, 0 skipped, 0 xfailed, 31 warnings (all third-party/env deprecations) |
| 5 | `git diff --stat -- app/utils/monitoring.py tests/conftest.py migrations/` | **empty** (all three protected areas) |
| 6 | `git diff -U0` hunk review of `external_platforms.py` | no hunk touches `_mock_directions` body; correction hunk confined to `_circuit_state` |

Failure classification (full suite): the 2 failures are both
`test_marketplace_ux_harmonisation.py` owner-review tests failing with HTTP 302
(login-redirect) where 200 / (403, 404) was expected — same file and same 302
symptom class as the established baseline (74 passed + 2 pre-existing). The
failing file contains **zero** references to `direction|circuit|external_platforms|redis`
(verified by file-scoped search), and Fix 2.2's production change is confined to
`external_platforms.py` directions internals ⇒ **PRE-EXISTING**, not a Fix 2.2
regression. Fix 2.2 regression check: provider success (T6), mock fallback
(T2/T5/T9/T11), missing-key (T5), local-defect propagation (T4), provider
isolation (T1/T8), Redis fail-open (T7), existing transport services (rest of
suite green) — all verified.

Audit note — test-count delta:

The established baseline was 76 tests represented by 74 passed plus
2 pre-existing failures. The current full transport run collected
105 tests.

Fix 2.2's new test file contributes 16 collected tests. The remaining
+13 are attributable to concurrent foreign changes under tests/transport
(including the modified test_moderator_actions.py and other concurrent
test changes visible in the working tree), but this delta was not
reconciled test-by-test.

This is an audit note only. It does not alter the Fix 2.2 failure
classification: the two observed marketplace owner-review failures
remain PRE-EXISTING based on the direct file/path/symptom evidence already
recorded.

## 7. Residual risk

- Same-instant `INCR`-between-read-and-claim is consumed by the recovery `DEL`
  (same exposure class as the pre-existing delete-on-recovery/delete-on-success
  design; no lock permitted by contract).
- The 2 pre-existing marketplace 302 failures remain open in the foreign
  working tree (owner-review auth flow; outside Fix 2.2 scope).
- `GOOGLE_MAPS_API_KEY` / `MAPBOX_ACCESS_TOKEN` production injection still
  UNKNOWN per contract D-ProdKeys (no config keys added, per contract).

## 8. Follow-ups (deferred, not in scope)

- Marketplace owner-review 302 failures (foreign area; needs its own node).
- Thundering-herd provider-call behavior explicitly deferred by contract:240.
- Production key injection (D-ProdKeys UNKNOWN) whenever the directions path
  gains a caller (D-Dormancy note).
