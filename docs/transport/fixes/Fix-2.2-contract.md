# Fix Contract — Fix 2.2 — External-Service Circuit Breakers (CONTRACT-ONLY)

**Owner:** [human]
**Date:** 2026-09-23
**Status:** CONTRACT PHASE — READY FOR HUMAN REVIEW (no implementation authorized yet)
**Roadmap reference:** Edition 2.0, Part VII Fix 2.2 (`docs/transport/00-MANIFESTO-EDITION-2.0.md:463-475`), Part XXX "done" spec (`:3732-3750`), architecture findings #12 (`:2387-2389`) and §7 (`:2681-2695`)
**Report format:** Compact (contract gate)

Evidence tags used throughout: **FOUND** = read directly from repository/roadmap; **INFERRED** = reasoned from evidence but not stated; **UNKNOWN** = no repository or specification evidence.

---

## 1. Problem

`ExternalPlatformsService.get_directions()` (`app/transport/services/external_platforms.py:53-83`) makes outbound `requests.get(..., timeout=10)` calls to Google Maps (`:108`) and Mapbox (`:162`) with:

- no retry (FOUND — roadmap finding #12, confirmed by reading the code);
- no circuit breaker (FOUND — `@with_circuit_breaker` exists in `app/utils/monitoring.py:139-190` but is applied to **zero** call sites anywhere in the repository, and it is process-local closure state, not Redis-backed);
- silent degradation to `_mock_directions()` on every provider exception (FOUND — `:136-139`, `:180-182`);
- outer `except Exception` at `:78-83` converting **every** exception — including `ValidationError("UNSUPPORTED_PROVIDER")` raised at `:73-76` and any programmer defect — into `ServiceUnavailableError("DIRECTIONS_UNAVAILABLE")` (FOUND).

Consequence (roadmap, `:3736-3738`): if the provider is slow, every directions call blocks a worker thread up to 10 s; if it is down, every call pays the full timeout before degrading; failures are indistinguishable from programmer defects; the same failure repeats on every call because nothing is remembered between calls.

Roadmap "done" (`:3740-3747`, FOUND): a Redis-backed circuit breaker decorator `@circuit_breaker("google_maps", failure_threshold=5, recovery_timeout=30)`; while open, `_get_google_directions()` returns mock data immediately without calling Google; circuit-state metrics exposed for the dashboard.

---

## 2. Existing behavior

### 2.1 Call path (single-file claim)

| Step | Location | Behavior | Tag |
|---|---|---|---|
| Entry | `external_platforms.py:53` `get_directions(origin, destination, provider='google')` | `@monitor_endpoint("get_directions")` wraps with `MonitorContext` (log-only, does not suppress exceptions — `monitoring.py:45`) | FOUND |
| Dispatch | `:67-76` | `provider=='google'` → `_get_google_directions`; `'mapbox'` → `_get_mapbox_directions`; else `ValidationError` | FOUND |
| Outer catch | `:78-83` | any `Exception` logged, re-raised as `ServiceUnavailableError(code="DIRECTIONS_UNAVAILABLE")` | FOUND |
| Google leg | `:86-139` | no `GOOGLE_MAPS_API_KEY` in config → `_mock_directions` immediately (`:89-92`); else `requests.get(timeout=10)`; non-`OK` status raises; any exception → `_mock_directions` (`:136-139`) | FOUND |
| Mapbox leg | `:142-182` | same shape with `MAPBOX_ACCESS_TOKEN` (`:145-147`, `:180-182`) | FOUND |
| Fallback | `:185-207` `_mock_directions` | deterministic haversine-less approximation, returns `success: True, provider: 'mock', polyline: None` | FOUND |
| Singleton | `:390-397` `get_external_platforms()` | re-exported via `app/transport/services/__init__.py:21` and `app/transport/__init__.py:65-66` | FOUND |

### 2.2 Duplicate/dead paths (do not touch)

- `app/transport/services/future_adds.py:165-223` defines a second `MapsService.get_directions` and second `ExternalPlatformsService`. It is **not imported anywhere** (FOUND — repository-wide import grep empty) and its file tail is a dangling string literal; `import random` is commented out (`:5`) while `MapsService.get_directions` calls `random.randint`. **INFERRED:** dead code; out of scope; must not become the canonical fallback.

### 2.3 Existing circuit-breaker primitive

`with_circuit_breaker` (`monitoring.py:139-190`, FOUND):

- process-local `nonlocal` counters — not shared across workers, not Redis-backed;
- `expected_exceptions=(Exception,)` — counts programmer defects;
- after `reset_timeout` it unconditionally resets to closed (`:159-164`) — no trial call, no distinct HALF-OPEN state (log line says "half-open" but state variable is already `False`);
- raised `ServiceUnavailableError` when open (`:166-170`) — it does **not** invoke a fallback;
- imported by `settings_service.py:34` and `provider_service.py:50` but **never applied** (`@with_circuit_breaker` — zero matches repo-wide).

**INFERRED:** it cannot satisfy the roadmap spec as-is (not Redis-backed, hides bugs, no fallback path). Whether to extend it or write a new decorator is an open decision (§12).

### 2.4 Configuration

- `GOOGLE_MAPS_API_KEY` / `MAPBOX_ACCESS_TOKEN` are read only via `current_app.config.get(...)` (`:89`, `:145`, `:215`); **no definition exists** in `app/config.py` and **no entry exists** in `.env`, `.env.local`, `.env.prod`, `.env.docker`, `.env.testing` (FOUND — direct grep). In every currently-evidenced environment the key is `None`, so the Google/Mapbox legs short-circuit to mock **before any network call** (FOUND).
- **UNKNOWN:** whether production injects these keys by other means (platform env, secrets manager). The contract must not assume either way.

### 2.5 Redis client

- `app/extensions.py:102` `redis_client = LazyRedis()` (FOUND).
- Established Redis failure pattern precedent: `app/events/routes.py:86-102` `rate_limit()` — `None` client → warning + **fail open**; exception → warning + **fail open** (FOUND).
- Analytics precedent: never raise on Redis failure, return empty/zeroed results (`app/utils/analytics.py:241`, FOUND).

### 2.6 Callers, tests, observability

- Callers of `get_directions(`: **none** in production code (FOUND — repo-wide grep matches only the three definitions). `get_external_platforms()` likewise has no call sites outside module exports. Fare estimation goes through `fare_service.calculate_estimate` (`app/transport/routes.py:251-252`), not this path.
- Tests referencing `external_platforms` / `get_directions` / `_mock_directions` / circuit: **none** (FOUND — tests/ grep empty).
- Observability today: `monitor_endpoint` log lines and `record_metric` (`monitoring.py:107-111`) which is `logger.info` only (FOUND). No dashboard endpoint exposes circuit state (UNKNOWN — none found).

### 2.7 Response-shape divergence (preserve as-is)

| Source | Keys |
|---|---|
| Google (`:119-134`) | `success, distance_meters, distance_text, duration_seconds, duration_text, polyline, steps` — **no** `provider` |
| Mapbox (`:172-178`) | `success, distance_meters, duration_seconds, polyline, provider='mapbox'` — no `*_text`, no `steps` |
| Mock (`:198-207`) | `success, distance_meters, distance_text, duration_seconds, duration_text, polyline=None, provider='mock', note` |

All three carry `success: True` (FOUND). No consumer exists in-repo (§2.6), but shapes must not be silently normalized in this node.

### 2.8 State table — current behavior

| # | State / condition | On entry | Observable result | Tag |
|---|---|---|---|---|
| S1 | CONFIGURED (key present) + provider healthy | outbound call, ≤10 s | provider-shaped dict | FOUND |
| S2 | CONFIGURED + provider error/timeout/non-OK | full timeout then except | `_mock_directions` dict (success:True, provider:'mock') | FOUND |
| S3 | NOT CONFIGURED (key `None`, the evidenced state) | no network call | `_mock_directions` dict | FOUND |
| S4 | Unsupported `provider` arg | `ValidationError` raised | converted by `:78` to `ServiceUnavailableError` | FOUND |
| S5 | Programmer defect inside leg (e.g. `KeyError` on payload) | caught by broad `except` | falls to `_mock_directions` (Google/Mapbox legs) — **bug masked as success** | FOUND |
| S6 | Memory of past failures | none | every call retries the provider from scratch | FOUND |
| S7 | Circuit state (any) | no circuit exists | n/a | FOUND |
| S8 | HALF-OPEN | state does not exist; roadmap does not name it | n/a | FOUND (absence) |
| S9 | Redis involvement in this path | none | n/a | FOUND |
| S10 | Behavior when provider configured-and-slow in production | UNKNOWN — no evidenced environment has keys | UNKNOWN | UNKNOWN |

---

## 3. Intended behavior

After implementation (not authorized in this phase):

1. Outbound directions calls are guarded per provider (`google_maps`, `mapbox`) by a **Redis-backed circuit breaker** (roadmap `:3742`, FOUND).
2. Defaults taken from the roadmap spec, not invented: `failure_threshold=5`, `recovery_timeout=30` (`:3743`, FOUND).
3. While a provider's circuit is open, the directions leg returns `_mock_directions(origin, destination)` **immediately, without issuing the HTTP request** (`:3744-3746`, `:2692-2693`, FOUND).
4. Only **provider/dependency failures** advance the failure counter (§5).
5. Circuit state transitions and current state are observable (logged + metric), per `:3747` (FOUND); dashboard exposure is an open decision (§12).
6. Timeout remains 10 s per attempt (FOUND — current code; no roadmap change).
7. Behavior in states S3 (no key) is unchanged: immediate mock, no network, no circuit counting required (it is not a provider failure). **INFERRED:** no counter increment when no outbound call is attempted.
8. The outer `except Exception → ServiceUnavailableError` conversion is narrowed so local defects are not disguised as provider outages (§5).

---

## 4. State machine

States (only those justified by evidence; no invented states):

| State | Definition | Evidence |
|---|---|---|
| CLOSED | calls pass through to provider leg; failures counted | FOUND (roadmap implies baseline) |
| OPEN | failures ≥ `failure_threshold`; calls short-circuit to `_mock_directions` | FOUND (`:3742-3746`) |
| HALF-OPEN | **NOT ADOPTED in v1** — roadmap never names it; existing primitive only logs the phrase while already closed (`monitoring.py:163`) | FOUND (absence) |

Transitions (proposal grounded in roadmap vocabulary "circuit open → recovery", `:472-473`):

```
CLOSED --(N = failure_threshold counted failures)--> OPEN
OPEN   --(recovery_timeout elapsed)--> CLOSED      (unconditional reset,
                                                     matching the existing
                                                     primitive's semantics at
                                                     monitoring.py:159-164)
CLOSED --(any success)--> CLOSED                   (counter reset)
```

**NEEDS PRODUCT/ARCHITECTURE DECISION:** whether a trial/half-open call is required after `recovery_timeout` instead of unconditional close (§12, D3). Until decided, the contract specifies CLOSED↔OPEN only; implementing a HALF-OPEN state without that decision is prohibited.

Invariants (contractual):

- I1: In OPEN, zero HTTP requests are issued to that provider (roadmap `:3745`, FOUND).
- I2: Failure counting is **per provider name** (`google_maps` vs `mapbox` isolation) — INFERRED from the decorator signature `@circuit_breaker("google_maps", ...)` (`:3743`, FOUND as evidence of naming, isolation as inference).
- I3: A circuit for provider A never short-circuits provider B.
- I4: Circuit state survives process restart and is shared across workers (Redis-backed, `:3742`, FOUND).
- I5: Programmer defects never increment the failure counter and never transition state (§5).

---

## 5. Failure semantics

Classification (mandatory — the circuit must not hide bugs):

| Class | Examples in this path | Counts toward threshold? | Current behavior | Contract behavior |
|---|---|---|---|---|
| **Provider/dependency failure** | `requests` `Timeout`/`ConnectionError`; HTTP 4xx/5xx via `raise_for_status`; Google `status != 'OK'` (`:112-113`); Mapbox `code != 'Ok'` (`:166-167`); JSON decode failure of a **provider** response | **Yes** | logged → `_mock_directions` | logged + counted; fallback to `_mock_directions` preserved |
| **Configuration absence** | key/token is `None` (`:89-92`, `:145-147`) | **No** (no outbound call attempted) | immediate `_mock_directions` | unchanged; optionally logged once — INFERRED |
| **Local validation defect** | `ValidationError` unsupported provider (`:73-76`); missing `origin['latitude']` `KeyError` in `_mock_directions` (`:191-193`) | **No** | converted to `ServiceUnavailableError` (`:78-83`) or masked by leg-level `except` | must propagate as-is (or as 4xx for validation); never counted; never converted into a provider-outage signal |
| **Programmer defect / contract violation of provider payload** | `KeyError`/`IndexError`/`TypeError` parsing a provider payload (`:116-133`, `:170-178`) when the payload shape itself is unexpected | **No** | masked → mock | must **not** be swallowed into mock success: raise/log as defect so tests and monitoring see it. **NEEDS PRODUCT/ARCHITECTURE DECISION** whether the parse-defect path raises or degrades-with-error-log (§12, D4) — rationale: distinguishing "provider sent garbage" (dependency) from "our parser is wrong" (defect) requires per-exception typing; blanket `except Exception` is prohibited |
| **Redis unavailability** | circuit state read/write fails | **No** | n/a (Redis unused) | §6 fail-open; no state transition attempted |

Explicit rules:

- F1: The circuit decorator observes only exceptions in the classified **provider** set (or an explicit success/failed return from the leg). `expected_exceptions` must not be `(Exception,)`.
- F2: `get_directions`' outer blanket handler (`:78-83`) must not convert `ValidationError` or local defects to `ServiceUnavailableError`.
- F3: A degraded mock response remains `success: True, provider: 'mock'` (FOUND current shape) so existing consumers cannot tell the difference **unless** §12-D5 decides otherwise — the `note` key is the existing disclosure channel (`:206`, FOUND).
- F4: Failures **while the circuit is OPEN** do not accrue (no call is made).

---

## 6. Redis state

All values below are proposals unless tagged; no numeric value appears in this contract unless it comes from the roadmap or current code.

| Key (proposal) | Type | Purpose | Evidence |
|---|---|---|---|
| `transport:circuit:<name>:failures` | counter (INCR) | consecutive counted failures | pattern: `rate_limit:{key}` INCR+EXPIRE (`events/routes.py:94-98`, FOUND) |
| `transport:circuit:<name>:state` | string `closed`/`open` | current state | NEEDS PRODUCT/ARCHITECTURE DECISION on exact key/namespace (D2) |
| `transport:circuit:<name>:opened_at` | epoch seconds | when OPEN began; drives `recovery_timeout` expiry | proposal |

- Thresholds: `failure_threshold=5`, `recovery_timeout=30` — **FOUND** (roadmap `:3743`). Any other value requires roadmap amendment.
- Atomicity/concurrency (proposal, needs confirmation — D2):
  - failure increment: `INCR` + `EXPIRE` (window ≥ `recovery_timeout`) in a pipeline — matches `events/routes.py:94-98` (FOUND precedent);
  - open transition: `INCR` result compared to threshold; state set with `SET ... EX recovery_timeout` so expiry itself drives recovery (proposal);
  - check-then-call is **not** transactional: N workers already past the check may still issue a provider call at the moment of transition. Contract accepts this bounded race (**at-least-once during transition**) rather than introducing a distributed lock — INFERRED acceptable; flag if architecture disagrees (D2).
  - Key TTL ensures orphan keys self-clean; no manual cleanup path (proposal).
- Redis unavailable / `redis_client` falsy / command exception: **fail open** — allow the provider call, log a warning, perform no state read/write. Grounded in two in-repo precedents: `events/routes.py:88-102` and `analytics.py` never-raise policy (FOUND). Fail-**safe** (serve mock whenever Redis is down) was considered and rejected for v1: it would silently disable a working provider whenever Redis blips, which no roadmap line calls for.
- Key naming/namespace and the exact open-with-TTL scheme are **NEEDS PRODUCT/ARCHITECTURE DECISION (D2)** — the table is a proposal, not a discovered fact.
- No migration, no new dependency for storage: reuse `app.extensions.redis_client` (FOUND pattern).

---

## 7. Fallback semantics

- The **one and only** fallback for an open circuit or a counted provider failure is `ExternalPlatformsService._mock_directions(origin, destination)` (`external_platforms.py:185`, FOUND; roadmap `:3744-3746` explicitly names it).
- `_mock_directions` is **not modified** by this node (its math, keys, and `provider: 'mock'` marker are preservation surface).
- No second fallback path may be introduced (no cached-last-success, no provider swap google↔mapbox, no synthetic error payload). Roadmap shows exactly one fallback line (`:2692-2693`, FOUND).
- `future_adds.py` mock must not be used (§2.2).
- The open-circuit fallback must be invoked **at the provider-leg layer** (`_get_google_directions` / `_get_mapbox_directions`) or immediately inside the decorator around those legs — either wiring satisfies `:3744` ("`_get_google_directions()` immediately returns mock data"); the precise seam (decorator-return-value vs leg-guard) is an implementation detail decided at IMPLEMENTATION planning (D6), because the decorator must remain generic.
- S3 (no API key) keeps its existing immediate-mock path untouched.

---

## 8. Recovery semantics

- `recovery_timeout=30` seconds from the roadmap (FOUND) is the sole recovery trigger for v1; after it elapses the circuit returns to CLOSED and the failure counter resets (proposal matching `monitoring.py:159-164`, FOUND as precedent).
- On return to CLOSED, the next call is a **normal call** (no trial-call machinery in v1, §4). If it fails, it counts normally and re-opens after `failure_threshold` further failures.
- Any counted-failure sequence in CLOSED resets on the first success (FOUND precedent `monitoring.py:175-176`; standard breaker semantics).
- Redis expiry of `state`/`opened_at` is a **second, self-cleaning recovery path**: if TTL writes fail silently, key expiry lands in CLOSED-equivalent absence — acceptable and consistent with fail-open (proposal).
- No manual/admin reset endpoint in v1 (none exists; creating one is scope expansion — §12 D7).
- Geocoding (`geocode_address`, `:211-249`) shares the file and identical defect pattern but is **not** guarded by this node unless §12-D1 expands scope.

---

## 9. Preservation rules

Must remain byte-identical or behavior-identical after implementation:

1. `_mock_directions` body and return shape (`:185-207`).
2. Google/Mapbox success payload shapes and the three-way divergence (§2.7).
3. `timeout=10` per outbound attempt (`:108`, `:162`).
4. `@monitor_endpoint("get_directions")` remains on the entry function; decorator **ordering** (monitor outside breaker vs breaker outside monitor) decided at implementation planning — either preserves monitoring logs (D6).
5. Singleton `get_external_platforms()` and all module exports (`services/__init__.py`, `transport/__init__.py`).
6. `geocode_address`, `send_sms`, `process_payment_external` — untouched (their defects are follow-ups, §11).
7. `future_adds.py` — untouched.
8. `app/utils/monitoring.py::with_circuit_breaker` — either reused-with-fix or left untouched; must not be half-modified (D5).
9. No migration (§20 red line — none needed: Redis only).
10. No wallet/KYC/conftest/model changes.
11. Existing test suite green: baseline 74 passed + 2 pre-existing failures (`test_marketplace_ux_harmonisation`).
12. No commits; human executes any future implementation gate.
13. S3 short-circuit (no key → immediate mock, no HTTP) preserved.
14. Response `success: True` on mock fallback preserved (F3).

---

## 10. Test obligations

New file (proposed): `tests/transport/test_directions_circuit_breaker.py`. Shared fixtures untouched (`tests/conftest.py` red line). Required cases:

| # | Obligation | Asserts |
|---|---|---|
| T1 | threshold trip | 5 counted provider failures → state OPEN |
| T2 | open short-circuit | while OPEN, provider `requests.get` is **not** invoked (monkeypatch/spy) and result equals `_mock_directions` output shape |
| T3 | recovery | after `recovery_timeout`, circuit CLOSED, provider called again (clock injected or TTL window simulated) |
| T4 | isolation | `google_maps` OPEN does not short-circuit `mapbox` (I3) |
| T5 | failure classification | `ValidationError`, `KeyError` from local defect: counter unchanged, state unchanged, exception surfaces per §5 |
| T6 | success resets | 4 failures → success → 5 more failures needed (not 1) to open |
| T7 | Redis down | `redis_client=None` or raising → call proceeds (fail-open), warning logged, no state written |
| T8 | no-key path | S3 immediate mock, no counter increment, no HTTP |
| T9 | regression | full `tests/transport/` remains at baseline (74 pass / 2 known failures) |
| T10 | preservation | `_mock_directions` output keys unchanged; `app/utils/monitoring.py` diff examined per D5 |

Test doubles: inject/monkeypatch Redis and `requests.get` inside the new test file only — no conftest edits (pattern precedent: Fix 2.6 file-local autouse fixture).

Observability obligation: circuit state transitions emit a structured log line (state, provider, failure count); `record_metric`-style emission is acceptable v1 (it is log-only, `monitoring.py:107-111`, FOUND); a dashboard endpoint is **not** required for this node's gate (§12 D7).

---

## 11. Non-goals

- No implementation in this phase (contract gate only).
- No Fix 2.1 (surge) or Fix 2.3 (idempotency) work.
- No GEO architecture work; no fare-engine changes; fare estimation path (`fare_service`) untouched.
- No guard on `geocode_address` (unless D1 expands).
- No retries/backoff beyond the roadmap's unparameterized "bounded retries" goal — see D8; inventing retry counts here is prohibited.
- No HALF-OPEN trial state (D3).
- No admin circuit-reset endpoint, no dashboard UI (D7).
- No `pybreaker`/new dependency without explicit approval (D5).
- No changes to `with_circuit_breaker`'s other would-be users (`settings_service`, `provider_service` merely import it).
- No provider-response caching, no provider failover google↔mapbox.
- No config keys added (`GOOGLE_MAPS_API_KEY` loading stays as-is).
- No migration, no commit, no register/BACKLOG update in this phase.
- `future_adds.py` cleanup, `geocode_address` defect masking, response-shape normalization — recorded follow-ups, not this node.

---

## 12. Open decisions

| ID | Decision | Why open | Options |
|---|---|---|---|
| D1 | Scope of the decorator: directions only, or also `geocode_address` (identical pattern, same file)? | Roadmap "done" names only `_get_google_directions` (`:3744`); Part VII says "and similar calls" (`:465`) | directions-only (literal done-spec) / directions+geocode (Part VII reading) |
| D2 | Exact Redis key namespace, value encoding, TTLs, and acceptance of the check-then-call race | No key naming exists anywhere for circuits; proposal only | adopt proposal / specify different scheme |
| D3 | HALF-OPEN trial call vs unconditional close after `recovery_timeout` | Roadmap never names HALF-OPEN; instruction forbids inventing it | v1 unconditional close (proposal) / add trial state (requires roadmap amendment) |
| D4 | Payload-parse defects (`KeyError` on provider JSON): raise as defect vs degrade-with-error-log | "Provider sent garbage" vs "our parser is wrong" cannot be told apart without per-exception policy; blanket swallowing is what we are fixing | raise / degrade with ERROR-level log + metric (not counted) |
| D5 | Mechanism: new Redis-backed decorator (in `external_platforms.py` or a transport util) vs extend `monitoring.py::with_circuit_breaker` vs add `pybreaker` dependency | Existing primitive is in-process and blind (`(Exception,)`); pybreaker is suggested in roadmap prose (`:2687`) but a dependency | new Redis decorator (proposal, matches Fix 2.6 no-new-dependency precedent) / extend existing / pybreaker |
| D6 | Decorator seam: generic decorator returning fallback vs leg-level guard; monitor/breaker decorator ordering | Roadmap shows both `@circuit_breaker(...)` and "leg returns mock" (`:3742-3746`) | decorator-with-fallback-callback / decorator-throws-open-error caught by leg |
| D7 | "Metrics exposed for the dashboard" (`:3747`) — v1 = structured logs + `record_metric`, or an actual endpoint? | No circuit dashboard surface exists (UNKNOWN) | logs+metric only (proposal) / owner API endpoint (scope addition) |
| D8 | "Bounded retries" (`:471`) — count/backoff unspecified anywhere | No number in roadmap or code; instruction prohibits inventing numbers | defer retries to a follow-up node (proposal) / human specifies N + backoff |
| D9 | Whether an evidenced production environment actually sets the maps keys (§2.4 UNKNOWN) — affects whether S1/S2 are reachable today | Not discoverable from repo | human confirmation |
| D10 | Whether "no in-repo callers" (§2.6) means this path is dormant; if so, priority of the node vs wiring callers first | Roadmap still lists 2.2 as a Tier-2 production item (`:2433`) | proceed as specified (proposal) / re-prioritize |

---

## Contract quality gate (six challenges)

1. **Semantic:** Does the contract state what "directions unavailable" means, and separate it from local defects? — Yes: §5 classification table, F1-F4; provider outage → counted + mock fallback; local defect → surfaces, never counted, never renamed `DIRECTIONS_UNAVAILABLE`.
2. **State:** Is every state and transition evidence-tagged? Is HALF-OPEN handled honestly? — §4 table: CLOSED/OPEN adopted from roadmap; HALF-OPEN explicitly not adopted, gated on D3; invariants I1-I5.
3. **Failure:** Could a circuit hide a bug? — No: F1 forbids `except Exception` counting; T5 enforces it; D4 parks the one ambiguous case with an explicit default (not counted).
4. **Redis:** Are values invented? Are atomicity, concurrency, and Redis-down behavior defined? — Only roadmap numbers (5/30) are treated as requirements; key schema flagged D2/NEEDS DECISION; INCR+EXPIRE pipeline precedent cited; bounded transition race stated; fail-open defined with two in-repo precedents.
5. **Fallback:** Is there exactly one fallback, and is it the existing one? — §7: `_mock_directions` only; no competing path; `future_adds` excluded; S3 preserved.
6. **Preservation:** What must not change? — §9 lists 14 surfaces including shapes, timeout, exports, baseline suite, red lines (migration/wallet/conftest), and no-commit rule.

**GATE: PASS**

The contract is complete for review; the ten D-items are declared open decisions by design of this phase — none of them blocks human review of the contract, and none may be silently resolved during IMPLEMENTATION without human approval.
