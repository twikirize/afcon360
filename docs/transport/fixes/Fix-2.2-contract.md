# Fix Contract — Fix 2.2 — External-Service Circuit Breakers (REVISED, DECISIONS RESOLVED)

**Owner:** [human]
**Date:** 2026-09-23
**Status:** CONTRACT PHASE PASS — IMPLEMENTATION AUTHORIZED (all six decisions RESOLVED — 2026-09-23)
**Roadmap reference:** Edition 2.0, Part VII Fix 2.2 (`docs/transport/00-MANIFESTO-EDITION-2.0.md:463-475`), Part XXX "done" spec (`:3732-3750`), findings #12 (`:2387-2389`), §7 (`:2681-2695`)
**Revision note:** v1 assumed Google as canonical provider and treated the mock response's `success: True` too loosely. The revision made the architecture provider-neutral, added an explicit internal outcome classification, and added a Reachability section. Human decisions are now resolved (§ Open Human Decisions).

Evidence tags: **FOUND** = read from repository/roadmap; **INFERRED** = reasoned, not stated; **UNKNOWN** = no evidence. All formerly parked decisions are **RESOLVED — 2026-09-23**.

---

## 1. Problem

`ExternalPlatformsService.get_directions()` (`app/transport/services/external_platforms.py:53-83`) performs outbound `requests.get(..., timeout=10)` calls to a resolved external provider (currently Google `:108`, Mapbox `:162`) with:

- no retry and no circuit breaker (FOUND — `@with_circuit_breaker` exists at `app/utils/monitoring.py:139-190` but is applied to zero call sites and is process-local, not Redis-backed);
- no explicit outcome classification: every provider-leg `except Exception` (`:136-139`, `:180-182`) silently returns `_mock_directions(...)`, and the outer handler (`:78-83`) converts everything — including local `ValidationError` — into `ServiceUnavailableError("DIRECTIONS_UNAVAILABLE")`;
- failure memory of zero: every call re-attempts a failing provider from scratch.

Roadmap "done" (`:3740-3747`, FOUND): a Redis-backed circuit breaker; while open, the directions leg returns the existing mock immediately without calling the provider; circuit-state observability. The roadmap's decorator example names `google_maps` — retained here as **historical/spec evidence only**, not as the generic contract.

---

## 2. Existing behavior

### 2.1 Call path (single-file seam)

| Step | Location | Behavior | Tag |
|---|---|---|---|
| Entry | `:53` `get_directions(origin, destination, provider='google')` | `@monitor_endpoint` log wrapper (does not suppress, `monitoring.py:45`) | FOUND |
| Dispatch | `:67-76` | string `provider` selects `'google'` or `'mapbox'` leg; else `ValidationError` | FOUND |
| Outer catch | `:78-83` | blanket `except Exception` → `ServiceUnavailableError` | FOUND |
| Google leg | `:86-139` | no key → immediate `_mock_directions`; else HTTP; any exception → `_mock_directions` | FOUND |
| Mapbox leg | `:142-182` | identical shape with token | FOUND |
| Fallback | `:185-207` `_mock_directions` | returns `success: True, provider: 'mock'` | FOUND |
| Exports | `services/__init__.py:21`, `transport/__init__.py:65-66` | singleton accessor | FOUND |

There is **no provider-resolution layer today**: dispatch is a hard-coded if/elif on a string (`:68-71`, FOUND). The provider-neutral flow describes the contract's *logical* stages over the existing dispatch — it does not authorize building a provider registry or discovery integration in this node (§ Non-goals).

### 2.2 Dead duplicate path

`future_adds.py:165-223` defines a second directions implementation, is imported nowhere (FOUND), has a dangling string tail and a commented-out `random` import it depends on. Out of scope; must never become the fallback.

### 2.3 Existing circuit primitive

`with_circuit_breaker` (`monitoring.py:139-190`, FOUND): process-local counters; `expected_exceptions=(Exception,)` (would classify local defects as dependency failures); unconditional close after timeout while logging "half-open"; raises `ServiceUnavailableError` instead of invoking a fallback; applied nowhere. Cannot satisfy this contract unchanged. **Untouched by this node (D-Mechanism).**

### 2.4 Configuration

`GOOGLE_MAPS_API_KEY` / `MAPBOX_ACCESS_TOKEN` are read only via `current_app.config.get(...)` (`:89`, `:145`) and defined in no `app/config.py` entry and no `.env*` file (FOUND by direct grep). In every evidenced environment both are `None`, so legs short-circuit to mock before any network I/O. Production injection: UNKNOWN — **RESOLVED — 2026-09-23 (D-ProdKeys): document the assumption in evidence/record; add no config keys.**

### 2.5 Redis precedents

- `app/extensions.py:102` `redis_client = LazyRedis()` (FOUND).
- Fail-open precedent: `app/events/routes.py:86-102` (`None` client or exception → warn + allow) (FOUND).
- Never-raise precedent: `app/utils/analytics.py` (FOUND).

### 2.6 Response-shape divergence (preserve)

Google payload has `steps`/`*_text` but no `provider`; Mapbox has `provider` but no `*_text`; mock has `*_text`, `provider: 'mock'`, `note`. All three currently carry `success: True` (FOUND). Normalization is out of scope.

### 2.7 State table — current behavior

| # | Condition | Result | Tag |
|---|---|---|---|
| S1 | key configured + provider healthy | provider-shaped payload | FOUND |
| S2 | key configured + provider error/timeout | full timeout → `_mock_directions` (indistinguishable from success to caller) | FOUND |
| S3 | key absent (evidenced state) | immediate `_mock_directions`, no network | FOUND |
| S4 | unsupported `provider` argument | `ValidationError` → converted to `ServiceUnavailableError` | FOUND |
| S5 | local `KeyError`/`TypeError` inside leg parse | masked → `_mock_directions` | FOUND |
| S6 | past-failure memory | none | FOUND |
| S7-S9 | circuit state / HALF-OPEN / Redis in this path | none exist | FOUND (absence) |

---

## 3. Intended behavior (provider-neutral)

1. Every directions call passes through: external directions operation → existing provider dispatch → provider-specific HTTP operation → provider outcome → circuit decision → caller-visible response. The outcome is classified before any caller-visible response is constructed.
2. Circuit identity = **provider identity + operation identity**; no global "external services" circuit exists.
3. Circuit parameters, from roadmap only: `failure_threshold=5`, `recovery_timeout=30s`, OPEN → immediate existing fallback, Redis-backed shared state, observability (`:3742-3747`, FOUND).
4. Only `PROVIDER_FAILURE` outcomes touch the circuit. `CONFIGURATION_UNAVAILABLE` never counts and never resets an existing sequence. `LOCAL_DEFECT` never counts and never becomes mock output.
5. `_mock_directions()` remains the single fallback **result generator**; its `success: True` is a caller-compatibility marker of the fallback shape, **not** evidence that any external provider succeeded. The circuit must never infer provider success from `success == True`.
6. Timeout stays 10 s per attempt.

---

## Reachability

**What repository evidence proves (FOUND):**

- Zero call sites of `get_directions(` exist outside its own definitions; `get_external_platforms()` has no callers outside module exports (repo-wide grep).
- Zero tests referenced this path before this node.
- Fare estimation flows through `fare_service.calculate_estimate` (`app/transport/routes.py:251-252`) — a different path.
- The roadmap lists Fix 2.2 as a Tier-2 production item (`:2433`) and documents the defect as live architecture risk (`:2681-2695`, `:3732-3750`) (FOUND).

**Assessment:**

- The path is **dormant** as of today's repository state: reachable only through manual/internal invocation of the exported service.
- **RESOLVED — 2026-09-23 (D-Dormancy): proceed.** Do not add a caller. Record dormancy as an evidence note.
- The roadmap authorizes protecting this seam independently of caller count — the fix targets the file/operation, not a route (`:3734`, FOUND).

**Blocking?** No.

---

## Provider Outcome Model

```text
external directions operation
        ↓
existing provider dispatch          (if/elif on provider string; NO registry)
        ↓
provider-specific HTTP operation     (_get_<provider>_directions leg)
        ↓
provider outcome                     (internal classification, pre-normalization)
        ↓
circuit decision                     (only PROVIDER_FAILURE counts / reads state)
        ↓
caller-visible response              (provider payload OR _mock_directions OR escape)
```

Outcome classification — defined **inside the deliberate failure boundary of each leg** (typed except-clauses; never a bare `except Exception` feeding the circuit):

| Outcome | Determined by | Circuit effect | Response path |
|---|---|---|---|
| `PROVIDER_SUCCESS` | leg completes HTTP + parse of the provider payload per its declared success status | reset consecutive-failure counter (`DEL failures`) | provider-shaped payload returned as-is |
| `PROVIDER_FAILURE` | HTTP/network failure (`requests` `Timeout`/`ConnectionError`, `raise_for_status` HTTP error) **OR** provider-declared error/status (`data['status'] != 'OK'` `:112-113`, `data['code'] != 'Ok'` `:166-167`) — **RESOLVED — 2026-09-23 (D-InvalidPayload)** | INCR failures; at 5 → `SET state open EX 30` | `CircuitOpenError`/provider-failure propagation reaches the fallback boundary → `_mock_directions(...)` |
| `CONFIGURATION_UNAVAILABLE` | key/token is `None` (`:89-92`, `:145-147`) — no HTTP attempt | **no effect**: not counted, does not open, **does not reset an existing failure sequence** | `_mock_directions(...)` — unchanged S3 behavior |
| `LOCAL_DEFECT` | HTTP succeeded but our parser's expected shape is wrong (`KeyError`/`TypeError`/`IndexError`); `ValidationError` for unsupported provider; unrelated programming errors — **RESOLVED — 2026-09-23 (D-InvalidPayload)** | **no effect**; must escape | exception propagates to caller as-is; never `DIRECTIONS_UNAVAILABLE`; never mock |

**Mandatory failure-observation order (critical requirement):**

```text
provider failure → PROVIDER_FAILURE → circuit records failure (INCR/EXPIRE)
    → CircuitOpenError / provider-failure propagation reaches fallback boundary
    → _mock_directions(...)
```

NOT: provider failure → `_mock_directions(...)` swallowed inside the leg → decorator thinks the provider succeeded. Tests must demonstrate five provider failures actually increment the circuit.

Why the final mock response's `success=True` means nothing about the provider:

- Three distinct non-success outcomes funnel into the same caller-visible `_mock_directions` shape; the `success` key is a property of the fallback result generator, produced *after* the circuit decision.
- The circuit reads only the internal outcome at the failure boundary — it never inspects a response dict, never reads `success == True`, never treats `_mock_directions` output as `PROVIDER_SUCCESS`.
- Invariant O1: `PROVIDER_SUCCESS` is reachable only by returning the provider's own parsed payload; any path that constructed `_mock_directions` output is by definition not `PROVIDER_SUCCESS`.

**Classification boundary rule (F1):** typed except-clauses producing `PROVIDER_FAILURE` catch only the external-dependency exception surface (`requests.RequestException` family and explicit provider-status raises already present at the call sites — **no new exception hierarchy**). Everything else falling out of the leg is `LOCAL_DEFECT` by default. An explicit `except Exception` may exist only as the outermost `LOCAL_DEFECT` catcher that logs and re-raises — it must not feed the counter, must not feed the fallback, and must not convert to `ServiceUnavailableError`.

---

## Circuit Identity

```text
circuit namespace = provider identity + operation identity
transport:circuit:google:directions:failures
transport:circuit:google:directions:state
transport:circuit:mapbox:directions:failures
transport:circuit:mapbox:directions:state
```

- `<provider>` = actual dispatch strings `google` / `mapbox` (`:68-71`, FOUND); `<operation>` = `directions`.
- The roadmap's `@circuit_breaker("google_maps", ...)` example (`:3743`) is historical evidence of threshold/timeout values only.
- **Isolation proof (must hold and be tested):** advancing `google:directions` writes only `transport:circuit:google:directions:*`; `mapbox:directions` keys are untouched. Opening Google must not affect Mapbox. No wildcard/global key. Shared state across workers for the same pair is required; shared state across different pairs is prohibited.

---

## Failure classification

```text
PROVIDER_FAILURE        HTTP/network failure OR provider-declared error/status
        → counted (INCR failures; EXPIRE 60) → at 5: SET state open EX 30
        → fallback boundary produces _mock_directions(...)

CONFIGURATION_UNAVAILABLE   missing API key/token (no HTTP attempt)
        → not counted → does not open → does not reset an existing sequence
        → _mock_directions(...)

LOCAL_DEFECT            HTTP OK but our parser's expected shape wrong
                        (KeyError/TypeError/IndexError);
                        ValidationError (unsupported provider);
                        unrelated programming errors
        → not counted → no fallback → escapes to caller
```

**Prohibitions:**

- P1: `except Exception:` must not become the circuit's failure classifier. The counter is incremented only inside the typed `PROVIDER_FAILURE` handler.
- P2: No arbitrary/new exception classes; use types already raised at the observed call sites plus default-to-LOCAL_DEFECT.
- P3: The outer blanket handler must stop reclassifying `LOCAL_DEFECT` and validation paths as `ServiceUnavailableError`.
- P4: `LOCAL_DEFECT` must never be converted into mock output.

---

## State machine

| State | Meaning | Evidence |
|---|---|---|
| CLOSED | `state` key absent; calls reach the provider leg; counted failures accumulate | FOUND |
| OPEN | `state` key exists; failures ≥ 5 for this `(provider, directions)`; calls short-circuit to `_mock_directions` before any HTTP | FOUND (`:3742-3746`) |
| HALF-OPEN | **not adopted** | FOUND (absence) |

Transitions:

```text
CLOSED --(5 PROVIDER_FAILURE: INCR reaches 5)--> OPEN   [SET state open EX 30]
CLOSED --(PROVIDER_SUCCESS)--> CLOSED                    [DEL failures]
OPEN   --(state TTL expires)--> CLOSED                   [unconditional resume;
                                                          next request observes
                                                          key absent ⇒ CLOSED]
```

Invariants:

- I1: OPEN ⇒ zero HTTP attempts to that provider for that operation (`CircuitOpenError` at entry, before any leg call).
- I2: `CONFIGURATION_UNAVAILABLE` and `LOCAL_DEFECT` never change state or counters.
- I3: Namespace isolation per Circuit Identity.
- I4: State is Redis-shared across workers and survives restarts.
- I5: Recovery = unconditional resume on `state` TTL expiry — **RESOLVED — 2026-09-23 (D-Probe).** No HALF-OPEN, no probe, no lock, no single recovery worker.

---

## Concurrency

**Exact Redis contract — RESOLVED — 2026-09-23 (D-RedisKeys):**

```text
transport:circuit:<provider>:directions:failures    INCR; EXPIRE 60
transport:circuit:<provider>:directions:state       SET open EX 30
```

- Failure key: on each `PROVIDER_FAILURE`, `INCR` then `EXPIRE 60`. TTL 60 covers `failure_threshold=5` accrual around `recovery_timeout=30`.
- State key: when the INCR result reaches `5`, `SET ... state open EX 30`.
- State interpretation: **key exists ⇒ OPEN; key absent ⇒ CLOSED.** The TTL on `state` is the recovery clock.
- **Do not create `open_until`, `opened_at`, or any third circuit key.**
- Reset: `DEL failures` only on genuine `PROVIDER_SUCCESS`.
- Counter increment: `INCR` only — never application-layer read-modify-write.
- OPEN establishment: single decider = the worker whose `INCR` result equals 5 (plus the atomic `SET ... EX 30`).
- Transition bound: workers that read key-absent before the `SET` lands may complete in-flight calls; **no new attempt starts once the key is observed present**.
- **Recovery — RESOLVED — 2026-09-23 (D-Probe):** on TTL expiry every worker observes key absence and resumes normally (unconditional). No probe, no lock, no HALF-OPEN. Thundering-herd concern deferred to a future node if ever evidenced.
- Redis unavailable / falsy client / command error: **warn → fail open → permit the provider call**; perform no state read/write; Redis failure itself never increments the provider circuit. Precedent: `events/routes.py:88-102` (FOUND).

---

## Roadmap boundary

```text
failure_threshold = 5            (FOUND :3743)
recovery_timeout  = 30 seconds   (FOUND :3743)
OPEN → immediate existing fallback (_mock_directions)   (FOUND :3744-3746)
Redis-backed shared state        (FOUND :3742)
circuit observability            (FOUND :3747)
```

**Not invented:** retry counts, retry backoff, HALF-OPEN, dashboard endpoints, new provider integrations, provider registry, response normalization, geocode guarding, new callers.

**Observability — RESOLVED — 2026-09-23:** transition logging only at actual transitions:

- CLOSED→OPEN: log `provider`, `operation`, `failure_count`, `reason=threshold_reached` + `record_metric(...)`.
- OPEN→CLOSED: when the next request first observes the expired `state` key absent, log `provider`, `operation`, `reason=recovery_expired` (+ available failure-count information).
- No transition message on normal requests. No dashboard endpoint.

---

## Fallback semantics (`_mock_directions`)

- `_mock_directions()` is a **fallback result generator**, not an external-provider success signal:
  ```
  _mock_directions() output  ⊨  "a degraded response was constructed"
  _mock_directions() output  ⊭  "the external provider succeeded"
  ```
- Its current output (keys, values, `success: True`, `provider: 'mock'`, `note`) is **preserved unchanged** (body untouched).
- The circuit must never inspect `success == True` (or any response field) to conclude provider success.
- Single fallback: reached on `PROVIDER_FAILURE` (after counting) and `CONFIGURATION_UNAVAILABLE` (S3, unchanged), including via `CircuitOpenError` at entry. Never for `LOCAL_DEFECT`.
- No `reason` key added to fallback responses. No second fallback. `future_adds.py` mock prohibited.

---

## Preservation rules

1. `_mock_directions` body and output shape.
2. Google/Mapbox success payload shapes and their divergence.
3. `timeout=10` per attempt.
4. `@monitor_endpoint` remains on the entry function.
5. Singleton/exports unchanged.
6. `geocode_address`, `send_sms`, `process_payment_external` untouched.
7. `future_adds.py` untouched.
8. `app/utils/monitoring.py` untouched (**D-Mechanism — RESOLVED — 2026-09-23**).
9. No migration; models untouched.
10. No wallet/KYC/`tests/conftest.py`/`app/models/base.py` changes.
11. No commits; no master-register update.
12. S3 (no key → immediate mock, no HTTP, no count, no reset) preserved.
13. No new caller, no config keys, no retries, no HALF-OPEN, no locks, no response normalization, no `reason` in responses.

---

## Architectural dependencies (reported, NOT implemented)

None required: the existing if/elif dispatch suffices as the "resolved provider" stage. A provider-registry, if ever wanted, is a separate node. Dormancy is an evidence note only (D-Dormancy resolved: proceed without a caller).

---

## Test obligations (IMPLEMENTATION phase — authorized)

New file only: `tests/transport/test_directions_circuit_breaker.py`; file-local fixtures only; no `tests/conftest.py` changes.

| # | Obligation |
|---|---|
| T1 | Five provider failures open provider A only; demonstrates failures actually increment the circuit |
| T2 | OPEN ⇒ zero provider HTTP attempts; output shape == `_mock_directions` |
| T3 | `state` TTL expiry resumes CLOSED (unconditional) |
| T4 | `LOCAL_DEFECT` (`KeyError`/`TypeError`/`IndexError`/`ValidationError`) escapes; counter unchanged; no mock |
| T5 | Missing key → mock; no HTTP; not counted; does not falsely reset an existing failure sequence |
| T6 | Genuine provider success resets the failure sequence (4 fail → success → 5 more fail to open) |
| T7 | Redis unavailable → warn → fail open → call proceeds; Redis failure never increments the circuit |
| T8 | Provider A circuit does not affect provider B (`google` vs `mapbox` keys) |
| T9 | `_mock_directions` output shape unchanged |
| T10 | Transition logging only at CLOSED→OPEN and OPEN→CLOSED |
| T11 | **Semantic proof:** mock `success=True` is never used as the provider-success signal |

---

## Non-goals

No retries, no HALF-OPEN, no locks, no new callers, no config keys, no geocoding/fare/GEO changes, no provider discovery, no response normalization, no dashboard endpoint, no migration/model changes, no `tests/conftest.py` changes, no commit, no master-register update, no touch to `monitoring.py`, `_mock_directions` body, `future_adds.py`, exports/singleton, `timeout=10`, `@monitor_endpoint`, configuration loading.

---

## Open Human Decisions

**All six decisions: RESOLVED — 2026-09-23. No open decisions remain.**

| ID | Resolution |
|---|---|
| D-Dormancy | **RESOLVED — 2026-09-23:** Proceed. Zero discovered production callers; do not add a caller; record dormancy as an evidence note. |
| D-Probe | **RESOLVED — 2026-09-23:** Unconditional resume. `state` expiry ⇒ `OPEN → CLOSED`. No HALF-OPEN, no probe, no lock, no single recovery worker. Thundering-herd = future node if ever evidenced. |
| D-RedisKeys | **RESOLVED — 2026-09-23:** Exactly `transport:circuit:<provider>:directions:failures` (INCR; EXPIRE 60) and `transport:circuit:<provider>:directions:state` (SET open EX 30). State = key-exists. No `open_until`/`opened_at`/third key. |
| D-Mechanism | **RESOLVED — 2026-09-23:** New decorator `circuit_breaker(provider_name)` inside `app/transport/services/external_platforms.py`. Do not touch `monitoring.py::with_circuit_breaker`. No `pybreaker`. |
| D-ProdKeys | **RESOLVED — 2026-09-23:** Production map-key injection remains UNKNOWN; document the assumption in evidence/record. No config keys added. |
| D-InvalidPayload | **RESOLVED — 2026-09-23:** HTTP/network failure OR provider-declared error/status → `PROVIDER_FAILURE` (counted). HTTP succeeds but our parser's expected shape is wrong → `LOCAL_DEFECT` (raises, not counted, no fallback). No new exception hierarchy. |

---

## Contract quality gate (six challenges)

1. **Semantic:** provider outcome precedes response construction; `success=True` decoupled from provider success (O1, T11); local defects no longer renamed `DIRECTIONS_UNAVAILABLE` (P3).
2. **State:** CLOSED/OPEN only; unconditional-resume recovery resolved (D-Probe); no HALF-OPEN.
3. **Failure:** three-class model; `except Exception` prohibited as classifier (P1); no invented exception hierarchy (P2); LOCAL_DEFECT escapes (P4); T4/T11 enforce.
4. **Redis:** exact two-key contract (D-RedisKeys); atomic `INCR`/`SET EX`/`GET`/`DEL`; transition bound stated; fail-open with two FOUND precedents; only roadmap numbers required.
5. **Fallback:** single existing generator; circuit never inspects response fields; S3 unchanged; `future_adds` excluded.
6. **Preservation:** 13 surfaces listed; scope exclusions explicit; dormancy declared and resolved.

**GATE: PASS**

All six human decisions are **RESOLVED — 2026-09-23**. The contract is provider-neutral and implementable without guessing: exact Redis keys, unconditional-resume recovery, file-local decorator, payload boundary, dormancy note, and production-key assumption are fixed. No silent choices remain (no lock, no HALF-OPEN, no Google-centric namespace, no trust of `success=True`, no third key, no `opened_at`).
