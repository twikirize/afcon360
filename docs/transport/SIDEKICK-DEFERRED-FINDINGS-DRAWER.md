# Sidekick — Deferred Findings Drawer (DFD)

**Status:** STANDALONE CAPTURE REGISTER — out-of-scope findings observed during Sidekick work.
**Scope:** Sidekick / Location Resolution Foundation / Location Lifecycle workstreams only.

## Rules (binding)

1. This drawer is a **capture mechanism, not authorization** to implement any finding recorded here.
2. A finding recorded here is **deferred unless its owning workstream explicitly authorizes it**. Recording ≠ approval.
3. A finding that prevents an *active* Sidekick requirement from working is **not** deferred to protect the schedule — it is resolved within the active item or the item is gated BLOCKED.
4. Potentially launch-critical safety, integrity, security, or data-loss concerns are **escalated for an explicit human decision**; they are never silently shelved here.
5. This drawer is kept **strictly separate** from: the Sidekick ten-item tracker, the A–L Master Roadmap, the Fine-Grade Attention Register, the UI/UX-HARDENING register, `BACKLOG.md`, and `GEO_DEFERRED_WORK_REGISTER.md`. Do not merge, renumber, replace, or claim progress in one register based on another.
6. The drawer is **never used to claim that an active Sidekick item is complete**.
7. Each finding carries a stable ID (`DFD-NN`), evidence, status/uncertainty, deferral reason, recommended next step, scope owner, and a launch-safety note.

---

## DFD-01 — Geocoding and search responsiveness

- **Evidence/source:** Prior live measurements recorded roughly 1.2–3.1 s per Geoapify forward/reverse request (browser + service-level evidence, October 2026). Current code: 300 ms client debounce (`static/js/modules/transport/dropoff-search.js`, pickup counterpart), `AbortController` + sequence guards, server 60/min budgets, per-adapter 10 s timeouts (`app/geo/providers/geoapify.py`, `app/geo/routes.py`). No result caching exists by explicit deferral.
- **Status:** Open, non-blocking. Uncertainty: none about the measurements; open about which optimization pays off.
- **Why deferred:** Deliberately deferred to keep the Sidekick ten-item sequence focused on correctness/integrity before performance.
- **Recommended investigation order (do not implement without authorization):**
  1. Evaluate smart geocoding caching and common-place handling.
  2. Evaluate faster autocomplete approaches and appropriate Geoapify autocomplete options.
  3. Reassess provider latency and relevance using measured evidence.
- **Scope owner:** GEO provider layer (`app/geo/`).
- **Launch safety:** Not launch-blocking at the ~100 riders/day operating target; revisit if latency degrades conversion or quota headroom.

## DFD-02 — Transient PostgreSQL connection termination

- **Evidence/source:** One ORM query encountered `server closed the connection unexpectedly` (October 2026 session); subsequent direct SQL checks, including `SELECT 1`, succeeded. No recurrence observed across the Item 2 proof runs (`tests/transport/test_location_lifecycle_booking_set.py`, 5 passed) or the regression suites run alongside them.
- **Status:** Open, cause **unknown**. Uncertainty: single incident; insufficient evidence for any infrastructure conclusion.
- **Why deferred:** Single transient with no recurrence and no affected test outcome; investigating a non-reproducible single blip would interrupt active items.
- **Recommended next step:** If it recurs or affects a focused suite, preserve the full failure evidence (query, backend logs, connection-pool state) and investigate; do not restart services or alter connection configuration without authorization.
- **Scope owner:** platform/database operations.
- **Launch safety:** Not declared an infrastructure defect. Escalate for explicit decision only on recurrence with impact.
