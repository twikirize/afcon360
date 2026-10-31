/**
 * AFCON360 Driver Dashboard — Production Candidate v2.5.2
 * Version: 2.5.2
 *
 * CHANGELOG from v2.5.1 (post-review patch pass):
 * - Fix: resumeDashboard() assigned to an undeclared `initToken` under
 *   "use strict", throwing ReferenceError on every BFCache pageshow and
 *   silently killing GPS/publish restart after back-navigation. Removed;
 *   the dataset guard (root.dataset.dashboardInitialized) is the only
 *   init guard needed.
 * - Fix: updateOnlineBadge() took a boolean but every caller passed a
 *   string ('Pending' / 'Offline' / 'Online'). Non-empty strings are
 *   truthy, so the driver-facing badge always rendered "Online," even
 *   when the driver had just gone off-duty. Signature changed to accept
 *   the label string directly.
 * - Fix: request() returned the raw server body on 2xx with no
 *   `success` key guaranteed. Every caller (offer accept/decline, trip
 *   actions, cash receipt, vehicle switch, availability toggle) gates on
 *   `.success`, so a backend 2xx body without an explicit `success` key
 *   was read as a failure. Now normalized: any 2xx becomes
 *   `{ success: true, ...body }` unless the body already sets `success`.
 * - Fix: offer-decline handler read `response.data.declined`, but
 *   request() returns the body flat — `response.data` was always
 *   undefined, making the check dead code. Now reads
 *   `response.declined` directly, matching the flat shape.
 * - Hardening: flashMsg() built its DOM with innerHTML + server-supplied
 *   text. Rebuilt with textContent for the message span so an echoed
 *   server string can't inject markup.
 *
 * INCORPORATES ALL 14 REVIEW FINDINGS FROM PRODUCTION CODE REVIEW:
 * F1  - Publishing scheduler pending schedule mechanism
 * F2  - GPS request tokens (fastFixToken, watchToken)
 * F3  - Retry-After zero handling and capped display
 * F4  - Five independent subsystem indicators
 * F5  - Stable observation timestamps + idempotency keys
 * F6  - GPS operational policy clarification
 * F7  - Health monitoring improvements
 * F8  - CSRF lifecycle scoping
 * F9  - Offline/online recovery preservation
 * F10 - Permission recovery test cases
 * F11 - Timeout/cancellation lifecycle testing
 * F12 - Retry policy backoff preservation
 * F13 - GPS initialization independent of CSRF
 * F14 - Initialization duplicate protection
 *
 * ARCHITECTURAL PRINCIPLES
 * - Health checks are informational only. They never gate GPS or publishing.
 * - GPS acquisition and location publishing have independent lifecycles.
 * - The location endpoint is the sole authority for publishing success.
 * - Every scheduler always has a defined next action; no silent dead ends.
 * - Auth and permanent rejections pause publishing; GPS continues.
 * - Network or lifecycle events never clear an auth/permanent pause.
 * - Every asynchronous callback is generation-guarded against BFCache.
 * - Location POSTs have a bounded timeout and cannot overlap.
 * - Every GPS request has a lifecycle-safe token.
 * - Initialization is idempotent and BFCache-safe.
 *
 * HTTP POLICY
 * 2xx        success         reset backoff, keep cadence
 * 400 csrf   transient       one bounded refresh+replay (see afconShouldRetryAfter400)
 * 400 other  classified      transient codes backoff; others pause
 * 401        auth            pause publishing; GPS continues
 * 403        authorization   pause publishing; GPS continues
 * 404        configuration   pause publishing; GPS continues
 * 408        transient       backoff
 * 409        conflict        skip observation; keep cadence
 * 422        validation      pause publishing; GPS continues
 * 429        rate-limited    honor Retry-After (max 300s); GPS continues
 * 5xx        server-error    backoff with jitter; GPS continues
 * network    connectivity    backoff with jitter; GPS continues
 *
 * RETRY POLICY
 * - Initial delay 5s, multiplier 2, max 60s, ±20% jitter.
 * - Retry-After cap: 300s. Zero is valid.
 * - GPS missing/stale: wait for fresh observation (5s polling).
 * - Success resets backoff to 5s.
 * - Every stop path either pauses (auth/permanent) or schedules a next attempt.
 * - Server Retry-After does not reset exponential progression.
 *
 * BACKEND CONTRACT (must match)
 * - POST /api/transport/drivers/{id}/location accepts { latitude, longitude, accuracy, client_ts, observation_id, idempotency_key }.
 * - Success: 200 or 204.
 * - Structured error body: { success:false, code:"<reason>", message:"..." }.
 * - 429/503 may include Retry-After header (seconds or HTTP date).
 * - Server-side dedupe / out-of-order rejection is authoritative.
 * - Do not return 2xx until durable persistence is committed.
 */

(function () {
    "use strict";

    // ============================================================
    // 1. PURE LOGIC — NODE TESTABLE
    // ============================================================
    var AFCON_FRESHNESS_MS = 5 * 60 * 1000;
    var AFCON_LOW_ACCURACY_M = 100;

    function afconValidObservation(lat, lon, acc) {
        return typeof lat === "number" && Number.isFinite(lat) && lat >= -90 && lat <= 90 &&
               typeof lon === "number" && Number.isFinite(lon) && lon >= -180 && lon <= 180 &&
               typeof acc === "number" && Number.isFinite(acc) && acc >= 0;
    }

    function afconShouldReplaceBest(current, candidate, nowMs) {
        if (!current) return true;
        if (!candidate || !(candidate.ts <= nowMs)) return false;
        if ((nowMs - current.ts) > AFCON_FRESHNESS_MS) return true;
        // A stale candidate should never evict a still-fresh current just
        // because it's more accurate — freshness matters more than a
        // marginally tighter accuracy on an old fix for a live location feed.
        if ((nowMs - candidate.ts) > AFCON_FRESHNESS_MS) return false;
        if (!(candidate.acc >= 0) || !(current.acc >= 0)) return false;
        if (candidate.acc <= current.acc * 0.80) return true;
        if (candidate.acc <= current.acc * 1.20 && candidate.ts > current.ts) return true;
        return false;
    }

    function afconShouldRetryAfter400(status, data) {
        if (status !== 400 || !data) return false;
        if (typeof data === "string") {
            try { data = JSON.parse(data); } catch (e) { return false; }
        }
        if (!data || typeof data !== "object") return false;
        return data.code === "csrf_expired" || data.code === "csrf_missing";
    }

    function afconClassifyResponse(status, data) {
        if (status >= 200 && status < 300) return "success";
        if (status === 400) {
            var code = (data && typeof data === "object") ? data.code : null;
            if (code === "rate_limited" ||
                code === "server_busy" ||
                code === "busy" ||
                code === "timeout" ||
                code === "retry_later") {
                return "transient-error";
            }
            return "permanent-error";
        }
        if (status === 401) return "auth-required";
        if (status === 403) return "authorization-failure";
        if (status === 404) return "configuration-error";
        if (status === 408) return "transient-error";
        if (status === 409) return "conflict";
        if (status === 422) return "validation-error";
        if (status === 429) return "rate-limited";
        if (status >= 500 && status < 600) return "server-error";
        return "permanent-error";
    }

    function afconParseRetryAfterMs(headerValue) {
        if (headerValue === null || headerValue === undefined) return null;
        var raw = String(headerValue).trim();
        if (!raw) return null;
        if (/^\d+$/.test(raw)) {
            var sec = parseInt(raw, 10);
            if (!Number.isFinite(sec)) return null;
            return Math.max(0, sec * 1000);
        }
        var t = Date.parse(raw);
        if (Number.isFinite(t)) return Math.max(0, t - Date.now());
        return null;
    }

    if (typeof module !== "undefined" && module.exports) {
        module.exports = {
            afconValidObservation: afconValidObservation,
            afconShouldReplaceBest: afconShouldReplaceBest,
            afconShouldRetryAfter400: afconShouldRetryAfter400,
            afconClassifyResponse: afconClassifyResponse,
            afconParseRetryAfterMs: afconParseRetryAfterMs,
            AFCON_FRESHNESS_MS: AFCON_FRESHNESS_MS,
            AFCON_LOW_ACCURACY_M: AFCON_LOW_ACCURACY_M
        };
        return;
    }

    // ============================================================
    // 2. PWA SERVICE WORKER REGISTRATION
    // ============================================================
    if ("serviceWorker" in navigator) {
        navigator.serviceWorker.register("/transport/sw.js", { scope: "/transport/" })
            .catch(function (err) {
                console.warn("[PWA] SW registration failed:", err);
            });
    }

    // ============================================================
    // 3. PWA INSTALL PROMPT
    // ============================================================
    window.__deferredInstallPrompt = null;

    window.addEventListener("beforeinstallprompt", function (e) {
        e.preventDefault();
        window.__deferredInstallPrompt = e;
        var btn = document.getElementById("installAppBtn");
        if (btn) btn.hidden = false;
    });

    window.addEventListener("appinstalled", function () {
        window.__deferredInstallPrompt = null;
        var btn = document.getElementById("installAppBtn");
        if (btn) btn.hidden = true;
    });

    (function setupInstallButton() {
        var btn = document.getElementById("installAppBtn");
        if (!btn || btn.dataset.installHandlerBound === "1") return;
        btn.dataset.installHandlerBound = "1";

        btn.addEventListener("click", async function () {
            var deferred = window.__deferredInstallPrompt;
            if (deferred) {
                deferred.prompt();
                try { await deferred.userChoice; } catch (e) { }
                window.__deferredInstallPrompt = null;
                btn.hidden = true;
                return;
            }
            var main = document.querySelector(".t-content");
            if (!main) return;
            var toast = document.createElement("div");
            toast.className = "alert alert-amber";
            toast.style.margin = "0 16px 16px";
            toast.innerHTML = '<i class="fa-solid fa-circle-info"></i>' +
                '<span style="flex:1;">Use your browser menu → Add to Home Screen</span>' +
                '<button class="alert-close" type="button" aria-label="Close">&times;</button>';
            toast.querySelector(".alert-close").addEventListener("click", function () {
                toast.remove();
            });
            main.prepend(toast);
            setTimeout(function () { toast.remove(); }, 6000);
        });
    })();

    // ============================================================
    // 4. DASHBOARD INITIALIZATION GATE
    // ============================================================
    var root = document.getElementById("driverDashboard");
    if (!root) return;

    var driverId = root.getAttribute("data-driver-id");
    if (!driverId) {
        console.warn("[AFCON] Missing driver ID.");
        return;
    }

    var pingInterval = parseInt(root.getAttribute("data-ping-interval") || "120", 10);
    if (!Number.isFinite(pingInterval) || pingInterval <= 0) pingInterval = 120;
    if (pingInterval > 300) pingInterval = 300;
    var PING_INTERVAL_MS = pingInterval * 1000;

    // ============================================================
    // 5. CENTRAL STATE
    // ============================================================
    var CSRF_TOKEN = null;
    var CSRF_ISSUED_AT = 0;
    var CSRF_REFRESH_PROMISE = null;
    var CSRF_REFRESH_TOKEN = null; // F8: lifecycle token for CSRF refresh

    var isOnline = root.getAttribute("data-is-online") === "1";
    var pageActive = true;
    var lifecycleGeneration = 0;

    // F14: duplicate-init guard lives on root.dataset.dashboardInitialized
    // (set once in initDashboard). No separate token variable is used.

    // Centralized publishing scheduler (F1, F8)
    var scheduleTimer = null;
    var scheduleKind = null;         // "interval" | "backoff" | "gps-wait" | null
    var publishToken = null;          // lifecycle-safe in-flight token
    var publishController = null;     // AbortController for the active POST
    var publishGeneration = 0;        // bumped by stopPublishing() (review-round-2 #6)
    var publishingPaused = false;
    var publishPauseReason = null;    // "auth" | "permanent" | null
    var pendingSchedule = null;       // F1: queued schedule during in-flight publish

    // Backoff
    var locationBackoff = {
        currentDelay: 5000,
        maxDelay: 60000
    };
    var BACKOFF_HARD_CAP_MS = 5 * 60 * 1000; // Retry-After / worst-case cap
    var GPS_WAIT_RETRY_MS = 5000;
    var PUBLISH_TIMEOUT_MS = 25000;
    var WATCHDOG_INTERVAL_MS = 15000;

    // GPS lifecycle tokens (F2, F9)
    var gpsActive = false;
    var fastFixToken = null;
    var watchToken = null;
    var fastFixInFlight = false;
    var watchId = null;
    var permWatcherBound = false;
    var blockedByPermission = false;

    // Health diagnostics (informational) (F7)
    var health = {
        status: "unknown",
        lastCheck: 0,
        dependencies: {}
    };
    var HEALTH_CHECK_URL = "/api/health/ping";
    var HEALTH_TIMEOUT_MS = 8000;
    var healthInFlight = null;
    var healthInFlightGen = -1;
    var healthInFlightToken = null;

    // Location state with stable identity (F5)
    var best = null;
    var lastKnown = null;
    var lastGeoCode = null;
    var observationIdCounter = 0;

    // C3: Session-scoped idempotency key to prevent collisions across reloads/tabs
    var SESSION_ID = (function () {
        try {
            if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
                return crypto.randomUUID();
            }
        } catch (e) {}
        return String(Date.now()) + "-" + String(Math.random()).slice(2, 10);
    })();

    var OPT_FAST = { enableHighAccuracy: false, timeout: 15000, maximumAge: 0 };
    var OPT_REFINE = { enableHighAccuracy: true, timeout: 30000, maximumAge: 0 };

    // Watchdog timer (F12)
    var watchdogTimer = null;

    // ============================================================
    // 6. CSRF MANAGEMENT (lifecycle-scoped, F8)
    // ============================================================
    function currentCsrfToken() {
        return CSRF_TOKEN ||
            document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
            "";
    }

    var CSRF_REFRESH_TIMEOUT_MS = 10000; // review-round-2 #1: bound the refresh fetch

    function refreshCsrfToken() {
        if (CSRF_REFRESH_PROMISE) return CSRF_REFRESH_PROMISE;

        var token = {};
        CSRF_REFRESH_TOKEN = token;

        CSRF_REFRESH_PROMISE = (async function () {
            var controller = new AbortController();
            var timeoutId = setTimeout(function () {
                try { controller.abort(); } catch (e) { }
            }, CSRF_REFRESH_TIMEOUT_MS);

            try {
                var resp = await fetch("/api/csrf-token", {
                    method: "GET",
                    headers: { "Accept": "application/json" },
                    credentials: "same-origin",
                    cache: "no-store",
                    signal: controller.signal
                });
                if (!resp.ok) return false;
                var data = await resp.json();
                if (!data || typeof data.csrf_token !== "string" || !data.csrf_token) return false;

                if (CSRF_REFRESH_TOKEN !== token) return false; // F8: stale refresh
                if (!pageActive) return false;

                CSRF_TOKEN = data.csrf_token;
                CSRF_ISSUED_AT = Date.now();
                var meta = document.querySelector('meta[name="csrf-token"]');
                if (meta) meta.setAttribute("content", CSRF_TOKEN);
                return true;
            } catch (e) {
                // Includes AbortError from the timeout above — resolves to
                // false rather than hanging, so afconPostWithCsrfRetry's
                // `await refreshCsrfToken()` always settles.
                return false;
            } finally {
                clearTimeout(timeoutId);
                CSRF_REFRESH_PROMISE = null;
                if (CSRF_REFRESH_TOKEN === token) CSRF_REFRESH_TOKEN = null;
            }
        })();

        return CSRF_REFRESH_PROMISE;
    }

    var csrfTimer = setInterval(function () {
        if (pageActive) refreshCsrfToken();
    }, 25 * 60 * 1000);

    // ============================================================
    // 7. HTTP POST (bounded by caller-supplied signal)
    // ============================================================
    function headers(json) {
        var h = {};
        if (json) h["Content-Type"] = "application/json";
        var token = currentCsrfToken();
        if (token) h["X-CSRFToken"] = token;
        return h;
    }

    async function postJSON(url, body, signal) {
        var resp = await fetch(url, {
            method: "POST",
            headers: headers(true),
            credentials: "same-origin",
            cache: "no-store",
            signal: signal,
            body: JSON.stringify(body || {})
        });

        var retryAfterMs = null;
        try {
            retryAfterMs = afconParseRetryAfterMs(resp.headers.get("Retry-After"));
        } catch (e) { /* headers unavailable */ }

        if (resp.status === 204) {
            return { status: 204, data: null, retryAfterMs: retryAfterMs };
        }
        var data = null;
        try { data = await resp.json(); } catch (e) { }
        return { status: resp.status, data: data, retryAfterMs: retryAfterMs };
    }

    async function afconPostWithCsrfRetry(url, buildBody, signal, gen) {
        var result = await postJSON(url, buildBody(), signal);
        if (!afconShouldRetryAfter400(result.status, result.data)) return result;

        if (signal && signal.aborted) return result;
        if (gen !== lifecycleGeneration) return result;
        if (!pageActive) return result;

        var refreshed = await refreshCsrfToken();
        if (!refreshed) return result;

        if (signal && signal.aborted) return result;
        if (gen !== lifecycleGeneration) return result;
        if (!pageActive) return result;

        return await postJSON(url, buildBody(), signal);
    }

    // ============================================================
    // 8. SUBSYSTEM INDICATORS (F4)
    // ============================================================
    function getSubsystemEl(id) {
        return document.getElementById(id);
    }

    function setSubsystemStatus(id, message, isError) {
        var el = getSubsystemEl(id);
        if (!el) return;
        el.className = isError ? "dc-toast err" : "dc-toast ok";
        el.textContent = message;
    }

    function setGpsStatus(message, isError) {
        setSubsystemStatus("dcGpsStatus", message, isError);
    }

    function setPublishStatus(message, isError) {
        setSubsystemStatus("dcPublishStatus", message, isError);
    }

    function setHealthStatus(message, isError) {
        setSubsystemStatus("dcHealthStatus", message, isError);
    }

    function setAuthStatus(message, isError) {
        setSubsystemStatus("dcAuthStatus", message, isError);
    }

    function setNetStatus(message, isError) {
        setSubsystemStatus("dcNetStatus", message, isError);
    }

    // Backward-compatible aggregate badge (F4)
    function setLocBadge(message, isError, showRetry) {
        var el = document.getElementById("dcLocBadge");
        if (!el) return;
        el.className = isError ? "dc-toast err" : "dc-toast ok";
        el.textContent = message;
        if (showRetry) {
            var btn = document.createElement("button");
            btn.type = "button";
            btn.className = "btn btn-sm btn-outline";
            btn.style.cssText = "margin-left:8px;padding:2px 8px;font-size:0.75rem;";
            btn.textContent = "Retry";
            btn.addEventListener("click", retryFromBadge);
            el.appendChild(btn);
        }
    }

    function geoErrorName(code) {
        if (code === 1) return "Permission denied";
        if (code === 2) return "Position unavailable";
        if (code === 3) return "Timeout";
        return "Unknown error (" + (code || "?") + ")";
    }

    function httpsBadge() {
        setGpsStatus("Location requires HTTPS. Open https://" + location.host, true);
        setLocBadge("Location requires HTTPS. Open https://" + location.host, true);
    }

    function syncOnline() {
        var toggle = document.querySelector("[data-online-toggle]");
        isOnline = toggle ? !!toggle.checked : root.getAttribute("data-is-online") === "1";
        root.setAttribute("data-is-online", isOnline ? "1" : "0");
        return isOnline;
    }

    // ============================================================
    // 9. HISTORICAL LOCATION SEED (display only; never published)
    // ============================================================
    function seedLastKnown() {
        var lat = parseFloat(root.getAttribute("data-last-lat"));
        var lon = parseFloat(root.getAttribute("data-last-lng"));
        if (!Number.isFinite(lat) || lat < -90 || lat > 90 ||
            !Number.isFinite(lon) || lon < -180 || lon > 180) return false;

        var accRaw = parseFloat(root.getAttribute("data-last-acc"));
        var acc = (Number.isFinite(accRaw) && accRaw > 0) ? accRaw : Infinity;
        var ts = Date.parse(root.getAttribute("data-last-ts") || "");

        lastKnown = { lat: lat, lon: lon, acc: acc, ts: Number.isFinite(ts) ? ts : 0 };
        renderAvailabilityBadge();
        return true;
    }

    // ============================================================
    // 10. LOCATION STATUS RENDERING (F4 - independent subsystems)
    // ============================================================
    function renderAvailabilityBadge() {
        // GPS subsystem
        if (blockedByPermission) {
            setGpsStatus("Location permission denied. Open browser site settings → Location → Allow.", true);
        } else if (best) {
            if (Date.now() - best.ts > AFCON_FRESHNESS_MS) {
                var ageS = Math.max(0, Math.round((Date.now() - best.ts) / 1000));
                var ageTxt = ageS < 60 ? ageS + "s ago" : Math.floor(ageS / 60) + "m ago";
                setGpsStatus("Location stale (last fix " + ageTxt + ").", true);
            } else if (best.acc > AFCON_LOW_ACCURACY_M) {
                setGpsStatus("Location available — low accuracy (±" + Math.round(best.acc) + "m).", false);
            } else {
                setGpsStatus("Location available (±" + Math.round(best.acc) + "m).", false);
            }
        } else if (lastKnown) {
            var seedAge = Math.max(0, Math.round((Date.now() - lastKnown.ts) / 1000));
            var seedAgeText = lastKnown.ts > 0
                ? (seedAge < 60 ? seedAge + "s ago" : Math.floor(seedAge / 60) + "m ago")
                : "time unknown";
            setGpsStatus("Approximate location (last fix " + seedAgeText + "). Refining…", true);
        } else {
            setGpsStatus("Location unavailable (" + geoErrorName(lastGeoCode) + ").", true);
        }

        // Network subsystem (independent of publish pause — always current, F4)
        setNetStatus(navigator.onLine ? "Online" : "Offline", !navigator.onLine);

        // Health subsystem (informational, independent of publish pause — F4/F7)
        if (health.status === "ok") {
            setHealthStatus("All systems operational.", false);
        } else if (health.status === "degraded") {
            setHealthStatus("Some dependencies degraded.", true);
        } else if (health.status !== "unknown") {
            setHealthStatus("Health check: " + health.status, true);
        }

        // Auth subsystem (baseline; the auth-pause branch below overrides
        // with a more specific message — review-round-3: this used to run
        // only at the bottom of the function, which the paused-publishing
        // early return skipped for every reason except "auth", so a 403/
        // 404/422 permanent pause left this frozen on a stale value).
        if (publishPauseReason === "auth") {
            setAuthStatus("Authentication required.", true);
        } else {
            setAuthStatus("Authenticated.", false);
        }

        // Publishing subsystem
        if (publishingPaused) {
            if (publishPauseReason === "auth") {
                setPublishStatus("Session expired. Please log in again.", true);
                setAuthStatus("Authentication required — publishing paused.", true);
            } else {
                setPublishStatus("Publishing paused by server.", true);
            }
            setLocBadge("Publishing paused. Click Retry or refresh.", true, true);
            return;
        }

        if (best && Date.now() - best.ts <= AFCON_FRESHNESS_MS) {
            var accText = best.acc > AFCON_LOW_ACCURACY_M ? " — low accuracy (±" + Math.round(best.acc) + "m)" : " (±" + Math.round(best.acc) + "m)";
            setPublishStatus("Publishing every " + pingInterval + "s" + accText + ".", false);
            setLocBadge("Location available" + accText + ". Publishing every " + pingInterval + "s.", false);
        } else {
            setPublishStatus("Waiting for fresh GPS fix…", true);
            setLocBadge(
                blockedByPermission
                    ? "Location permission denied."
                    : "Location unavailable. Retrying every " + pingInterval + "s.",
                true,
                blockedByPermission    // C6: show Retry when permission blocked
            );
        }
    }

    // ============================================================
    // 11. GPS INGESTION
    // ============================================================
    function ingestPosition(pos, nowMs) {
        if (!pos || !pos.coords) return false;
        var now = (typeof nowMs === "number") ? nowMs : Date.now();
        var lat = pos.coords.latitude, lon = pos.coords.longitude, acc = pos.coords.accuracy;
        if (!afconValidObservation(lat, lon, acc)) return false;

        // DOMTimeStamp is ms since epoch, so 0 (or negative) is junk, not a
        // real fix — left unguarded, a mock/buggy 0 would make best.ts = 0
        // forever "stale" and attemptPublish would gps-wait indefinitely.
        var ts = (typeof pos.timestamp === "number" && pos.timestamp > 0 && pos.timestamp <= now) ? pos.timestamp : now;
        var candidate = { lat: lat, lon: lon, acc: acc, ts: ts };

        if (afconShouldReplaceBest(best, candidate, now)) {
            best = candidate;
            renderAvailabilityBadge();
            return true;
        }
        return false;
    }

    function onAcquired(pos) {
        ingestPosition(pos);
    }

    function onAcquireError(err) {
        lastGeoCode = err ? err.code : null;
        if (window.isSecureContext === false) {
            httpsBadge();
            return;
        }
        if (err && err.code === 1) {
            blockedByPermission = true;
            stopGpsWatcher();
            watchPermissionResume();
            clearScheduleTimer();
            renderAvailabilityBadge();
            return;
        }
        if (!best) renderAvailabilityBadge();
    }

    // ============================================================
    // 12. PERMISSION RECOVERY (F10)
    // ============================================================
    function watchPermissionResume() {
        if (permWatcherBound) return;
        if (!navigator.permissions || !navigator.permissions.query) return;

        var gen = lifecycleGeneration;
        navigator.permissions.query({ name: "geolocation" }).then(function (status) {
            if (gen !== lifecycleGeneration) return;
            permWatcherBound = true;

            function handlePermissionState() {
                if (gen !== lifecycleGeneration) return;
                if (status.state === "granted" || status.state === "prompt") {
                    blockedByPermission = false;
                    setGpsStatus("Location permission restored. Resuming.", false);
                    if (!pageActive) return;
                    startGps();
                    if (syncOnline() && !publishingPaused) {
                        scheduleNextPublish(0, "interval");
                    }
                }
            }

            status.onchange = handlePermissionState;

            // F10: permission may already have changed between the error
            // that set blockedByPermission and this query resolving (e.g.
            // granted while the page was BFCache-paused). onchange only
            // fires on a future transition, so also check the state now.
            handlePermissionState();
        }).catch(function () { });
    }

    // ============================================================
    // 13. GPS LIFECYCLE (independent of publishing, F6, F9, F13)
    // ============================================================
    function canAcquireGps() {
        return pageActive && !blockedByPermission;
    }

    function startGps() {
        if (!canAcquireGps()) return;
        // F6, F13: GPS acquisition is independent of authentication/publishing.
        // Only respects driver's on-duty toggle (syncOnline) and permission.
        if (!syncOnline()) return;
        ensureWatch();
        kickFastFirst();
        gpsActive = true;
    }

    function stopGpsWatcher() {
        if (watchId !== null) {
            try { navigator.geolocation.clearWatch(watchId); } catch (e) { }
            watchId = null;
        }
        // F2: invalidate watch token
        watchToken = null;
        fastFixToken = null;        // C4
        fastFixInFlight = false;    // C4
        gpsActive = false;
    }

    function ensureWatch() {
        if (!pageActive || watchId !== null) return;
        if (!navigator.geolocation || !navigator.geolocation.watchPosition) return;
        var gen = lifecycleGeneration;
        var token = {};
        watchToken = token;
        try {
            watchId = navigator.geolocation.watchPosition(
                function (pos) {
                    if (watchToken !== token) return; // F2
                    if (gen !== lifecycleGeneration || !pageActive) return;
                    onAcquired(pos);
                },
                function (err) {
                    if (watchToken !== token) return; // F2
                    if (gen !== lifecycleGeneration || !pageActive) return;
                    onAcquireError(err);
                },
                OPT_REFINE
            );
        } catch (e) {
            watchId = null;
            watchToken = null;
        }
    }

    function kickFastFirst() {
        if (fastFixInFlight || !pageActive || blockedByPermission) return;
        if (!navigator.geolocation || !navigator.geolocation.getCurrentPosition) return;
        // F13: No syncOnline() guard here — GPS is independent.
        fastFixInFlight = true;
        var token = {};
        fastFixToken = token;
        var gen = lifecycleGeneration;
        try {
            navigator.geolocation.getCurrentPosition(
                function (pos) {
                    if (fastFixToken !== token) return; // F2
                    fastFixInFlight = false;
                    if (!pageActive || gen !== lifecycleGeneration) return;
                    ingestPosition(pos);
                    ensureWatch();
                },
                function (err) {
                    if (fastFixToken !== token) return; // F2
                    fastFixInFlight = false;
                    if (!pageActive || gen !== lifecycleGeneration) return;
                    onAcquireError(err);
                    if (!err || err.code !== 1) ensureWatch();
                },
                OPT_FAST
            );
        } catch (e) {
            fastFixInFlight = false;
            fastFixToken = null;
            ensureWatch();
        }
    }

    function retryLocationPermission() {
        if (fastFixInFlight || !pageActive) return;
        if (!navigator.geolocation || !navigator.geolocation.getCurrentPosition) return;

        blockedByPermission = false;
        permWatcherBound = false;
        fastFixInFlight = true;
        setGpsStatus("Requesting location permission…", false);

        var token = {};
        fastFixToken = token;
        var gen = lifecycleGeneration;
        try {
            navigator.geolocation.getCurrentPosition(
                function (pos) {
                    if (fastFixToken !== token) return; // F2
                    fastFixInFlight = false;
                    if (!pageActive || gen !== lifecycleGeneration) return;
                    ingestPosition(pos);
                    ensureWatch();
                    if (syncOnline() && !publishingPaused) {
                        scheduleNextPublish(0, "interval");
                    }
                },
                function (err) {
                    if (fastFixToken !== token) return; // F2
                    fastFixInFlight = false;
                    if (!pageActive || gen !== lifecycleGeneration) return;
                    onAcquireError(err);
                    renderAvailabilityBadge();
                },
                OPT_FAST
            );
        } catch (e) {
            fastFixInFlight = false;
            fastFixToken = null;
            blockedByPermission = true;
            renderAvailabilityBadge();
        }
    }

    // ============================================================
    // 14. CENTRALIZED PUBLISHING SCHEDULER (F1, F8)
    // ============================================================
    function clearScheduleTimer() {
        if (scheduleTimer !== null) {
            clearTimeout(scheduleTimer);
            scheduleTimer = null;
        }
        scheduleKind = null;
    }

    function resetBackoff() {
        locationBackoff.currentDelay = 5000;
    }

    function jitteredDelay(baseMs, maxMs) {
        var adjusted = Math.round(baseMs * (0.8 + Math.random() * 0.4));
        return Math.min(adjusted, maxMs);
    }

    function canSchedule() {
        if (!pageActive) return false;
        if (!navigator.onLine) return false;   // C5
        if (!syncOnline()) return false;
        if (blockedByPermission) return false;
        if (publishingPaused) return false;
        return true;
    }

    function scheduleNextPublish(delayMs, kind) {
        // F1: If a publish is in-flight, queue the next schedule
        if (publishToken) {
            pendingSchedule = {
                delay: delayMs,
                kind: kind || "interval"
            };
            return;
        }

        clearScheduleTimer();
        if (!canSchedule()) return;

        scheduleKind = kind || "interval";
        scheduleTimer = setTimeout(function () {
            scheduleTimer = null;
            scheduleKind = null;
            if (canSchedule()) attemptPublish();
        }, delayMs);
    }

    function scheduleBackoff(serverDelayMs) {
        if (!pageActive || publishingPaused) return;
        if (!navigator.onLine) return;              // C5: wait for online event

        var delay;
        if (typeof serverDelayMs === "number" &&
            Number.isFinite(serverDelayMs) &&
            serverDelayMs >= 0) { // F3: Retry-After: 0 is valid
            delay = Math.min(serverDelayMs, BACKOFF_HARD_CAP_MS);
        } else {
            delay = jitteredDelay(locationBackoff.currentDelay, locationBackoff.maxDelay);
            locationBackoff.currentDelay = Math.min(
                locationBackoff.currentDelay * 2,
                locationBackoff.maxDelay
            );
        }
        scheduleNextPublish(delay, "backoff");
    }

    function scheduleGpsWait() {
        if (!canSchedule()) return;
        scheduleNextPublish(GPS_WAIT_RETRY_MS, "gps-wait");
    }

    function stopPublishing() {
        clearScheduleTimer();
        pendingSchedule = null; // F1
        resetBackoff();

        // review-round-2 #6: an in-flight publish was previously left to
        // finish on its own — its completion could overwrite the "stopped"
        // status with a stale "Published…"/"retrying" message, or (if
        // connectivity flapped back before it resolved) sneak in a
        // reschedule. Abort it and bump publishGeneration so its handlers
        // recognize the stop and no-op, mirroring pauseDashboard().
        publishGeneration++;
        if (publishController) {
            try { publishController.abort(); } catch (e) { }
        }
        publishController = null;
        publishToken = null;
    }

    // ============================================================
    // 15. PAUSING (F3, F10)
    // ============================================================
    function pausePublishing(reason, message) {
        publishingPaused = true;
        publishPauseReason = reason;
        clearScheduleTimer();
        pendingSchedule = null; // F1
        resetBackoff();
        renderAvailabilityBadge();
        // GPS intentionally untouched.
    }

    function resumePublishingExplicitly() {
        publishingPaused = false;
        publishPauseReason = null;
        resetBackoff();
        if (!pageActive) return;
        if (!syncOnline()) { renderAvailabilityBadge(); return; }
        if (blockedByPermission) { retryLocationPermission(); return; }
        startGps();
        scheduleNextPublish(0, "interval");
    }

    // ============================================================
    // 16. LOCATION PUBLISHING (the authority, F1, F5, F8, F11)
    // ============================================================
    async function attemptPublish() {
        if (!pageActive) return;
        if (!syncOnline()) {
            renderAvailabilityBadge();
            return;
        }
        if (blockedByPermission) {
            renderAvailabilityBadge();
            return;
        }
        if (publishingPaused) {
            renderAvailabilityBadge();
            return;
        }
        if (publishToken) return;

        if (window.isSecureContext === false) {
            httpsBadge();
            return;
        }
        if (!navigator.geolocation) {
            pausePublishing("permanent", "Geolocation is not available in this browser.");
            return;
        }

        // Keep acquisition active; publishing and acquisition are independent.
        startGps();

        var now = Date.now();
        if (!best || now - best.ts > AFCON_FRESHNESS_MS) {
            renderAvailabilityBadge();
            scheduleGpsWait();
            return;
        }

        // F5: Stable observation identity for server-side dedupe
        var observationId = ++observationIdCounter;
        var snapshot = Object.freeze({
            lat: best.lat,
            lon: best.lon,
            acc: best.acc,
            ts: best.ts,
            observationId: observationId
        });

        if (!afconValidObservation(snapshot.lat, snapshot.lon, snapshot.acc) ||
            Date.now() - snapshot.ts > AFCON_FRESHNESS_MS) {
            renderAvailabilityBadge();
            scheduleGpsWait();
            return;
        }

        var gen = lifecycleGeneration;
        var pubGen = publishGeneration; // review-round-2 #6
        var token = {};
        publishToken = token;

        var controller = new AbortController();
        publishController = controller;

        var timeoutId = setTimeout(function () {
            try { controller.abort(); } catch (e) { }
        }, PUBLISH_TIMEOUT_MS);

        try {
            var url = "/api/transport/drivers/" + encodeURIComponent(driverId) + "/location";
            var result = await afconPostWithCsrfRetry(
                url,
                function () {
                    return {
                        latitude: snapshot.lat,
                        longitude: snapshot.lon,
                        accuracy: snapshot.acc,
                        client_ts: snapshot.ts,      // F5: stable timestamp
                        observation_id: observationId,
                        idempotency_key: "loc-" + driverId + "-" + SESSION_ID + "-" + observationId
                    };
                },
                controller.signal,
                gen
            );

            // review-round-2 #6: pubGen mismatch means stopPublishing() ran
            // while this request was in flight — the driver already got a
            // "stopped" status; don't let a stale success/error overwrite it
            // or reschedule behind its back.
            if (!pageActive || gen !== lifecycleGeneration || pubGen !== publishGeneration) return;

            var classification = afconClassifyResponse(result.status, result.data);

            if (classification === "success") {
                resetBackoff();
                var timeStr = new Date().toLocaleTimeString();
                if (snapshot.acc <= AFCON_LOW_ACCURACY_M) {
                    setPublishStatus("Published " + timeStr + " (±" + Math.round(snapshot.acc) + "m).", false);
                } else {
                    setPublishStatus("Published " + timeStr + " — low accuracy (±" + Math.round(snapshot.acc) + "m).", false);
                }
                renderAvailabilityBadge();
                scheduleNextPublish(PING_INTERVAL_MS, "interval");
                return;
            }

            if (classification === "auth-required") {
                pausePublishing("auth", "Session expired. Please log in again. GPS tracking continues.");
                return;
            }

            if (classification === "authorization-failure") {
                pausePublishing("permanent", "Publishing denied (403). GPS tracking continues. Contact support.");
                return;
            }

            if (classification === "configuration-error") {
                pausePublishing("permanent", "Publishing endpoint unavailable (404). GPS tracking continues.");
                return;
            }

            if (classification === "validation-error") {
                pausePublishing("permanent", "Publishing rejected (422). GPS tracking continues. Click Retry or refresh.");
                return;
            }

            if (classification === "permanent-error") {
                pausePublishing("permanent", "Publishing rejected (" + result.status + "). GPS tracking continues. Click Retry or refresh.");
                return;
            }

            if (classification === "conflict") {
                setPublishStatus("Observation skipped (conflict). Retrying next cycle.", false);
                scheduleNextPublish(PING_INTERVAL_MS, "interval");
                return;
            }

            if (classification === "rate-limited") {
                var wait = (typeof result.retryAfterMs === "number") ? result.retryAfterMs : null;
                var displayWait = wait !== null ? Math.min(wait, BACKOFF_HARD_CAP_MS) : null; // F3: cap display
                if (displayWait !== null) {
                    setPublishStatus("Rate limited (429). Retrying after " + Math.ceil(displayWait / 1000) + "s.", true);
                } else {
                    setPublishStatus("Rate limited (429). Retrying with backoff.", true);
                }
                scheduleBackoff(wait);
                return;
            }

            if (classification === "transient-error") {
                if (result.status === 408) {
                    setPublishStatus("Request timeout (408). Retrying with backoff.", true);
                } else {
                    setPublishStatus("Transient error (" + result.status + "). Retrying with backoff.", true);
                }
                scheduleBackoff();
                return;
            }

            if (classification === "server-error") {
                setPublishStatus("Server error (" + result.status + "). Retrying with backoff.", true);
                scheduleBackoff();
                return;
            }

            setPublishStatus("Location rejected (" + result.status + "). Retrying with backoff.", true);
            scheduleBackoff();

        } catch (err) {
            if (!pageActive || gen !== lifecycleGeneration || pubGen !== publishGeneration) return;
            if (controller.signal.aborted) {
                if (pageActive && gen === lifecycleGeneration) {
                    setPublishStatus("Publish request timed out. Retrying with backoff.", true);
                    scheduleBackoff();
                }
                return;
            }
            setPublishStatus(
                navigator.onLine
                    ? "Server unreachable. Retrying with backoff."
                    : "Device offline — publishing paused.",
                true
            );
            scheduleBackoff();
        } finally {
            clearTimeout(timeoutId);
            if (publishToken === token) {
                publishToken = null;
                // F1: Process any pending schedule queued during this publish
                if (pendingSchedule) {
                    var next = pendingSchedule;
                    pendingSchedule = null;
                    scheduleNextPublish(next.delay, next.kind);
                }
            }
            if (publishController === controller) publishController = null;
        }
    }

    // ============================================================
    // 17. RETRY FROM BADGE (explicit user action)
    // ============================================================
    function retryFromBadge() {
        if (blockedByPermission) {
            retryLocationPermission();
            return;
        }
        if (publishingPaused) {
            resumePublishingExplicitly();
            return;
        }
        if (!pageActive) return;
        if (!syncOnline()) { renderAvailabilityBadge(); return; }
        if (publishToken) return;
        if (scheduleTimer) return;
        startGps();
        scheduleNextPublish(0, "interval");
}

    // ============================================================
    // 19. NETWORK EVENTS (F9)
    // ============================================================
    window.addEventListener("offline", function () {
        if (!pageActive) return;
        stopPublishing();
        stopGpsWatcher();
        setNetStatus("Offline", true);
        setGpsStatus("Device offline — GPS paused.", true);
        setPublishStatus("Device offline — publishing paused.", false);
    });

    window.addEventListener("online", function () {
        if (!pageActive) return;
        setNetStatus("Online", false);

        // Always restart GPS on reconnect (acquisition is independent, F6, F13).
        startGps();

        // Resume publishing only if the user has not explicitly paused.
        if (publishingPaused) {
            renderAvailabilityBadge(); // F9: do NOT auto-resume after auth/permanent pause
        } else if (!blockedByPermission) {
            setPublishStatus("Network restored. Resuming…", false);
            scheduleNextPublish(0, "interval");
        } else {
            renderAvailabilityBadge();
        }

        checkHealthInBackground();
    });

    // ============================================================
    // 20. PAGE VISIBILITY
    // ============================================================
    document.addEventListener("visibilitychange", function () {
        if (!pageActive || document.hidden) return;

        // Schedule if the dashboard is online, unpaused, and nothing is pending.
        if (canSchedule() &&
            !scheduleTimer &&
            !publishToken &&
            (!best || Date.now() - best.ts > AFCON_FRESHNESS_MS)) {
            startGps();
            scheduleGpsWait();
        } else if (canSchedule() &&
                   !scheduleTimer &&
                   !publishToken &&
                   best &&
                   Date.now() - best.ts <= AFCON_FRESHNESS_MS) {
            startGps();
            scheduleNextPublish(0, "interval");
        }

        if (Date.now() - CSRF_ISSUED_AT > 20 * 60 * 1000) {
            refreshCsrfToken();
        }
    });

    // ============================================================
    // 21. BFCACHE LIFECYCLE (F1, F2, F8, F14)
    // ============================================================
    function pauseDashboard() {
        if (!pageActive) return;
        pageActive = false;
        lifecycleGeneration++;

        clearScheduleTimer();
        pendingSchedule = null; // F1
        stopGpsWatcher();
        stopWatchdog();

        if (publishController) {
            try { publishController.abort(); } catch (e) { }
        }
        publishController = null;
        publishToken = null;

        // F2: invalidate GPS tokens
        fastFixToken = null;
        fastFixInFlight = false;

        clearInterval(csrfTimer);
    }

    function resumeDashboard() {
        if (pageActive) return;
        pageActive = true;
        lifecycleGeneration++;

        // F14: initialization is guarded by root.dataset.dashboardInitialized
        // (set once in initDashboard). No additional token needed here.

        // Force fresh acquisition; do not publish the pre-BFCache fix.
        best = null;
        permWatcherBound = false;

        csrfTimer = setInterval(function () {
            if (pageActive) refreshCsrfToken();
        }, 25 * 60 * 1000);

        startWatchdog();

        if (!syncOnline()) {
            setGpsStatus("Offline — GPS paused.", false);
            setPublishStatus("Offline — publishing paused.", false);
            setNetStatus("Offline", true);
            return;
        }

        if (publishingPaused) {
            renderAvailabilityBadge();
            return;
        }

        if (blockedByPermission) {
            renderAvailabilityBadge();
            watchPermissionResume();
            return;
        }

        // F13: Start GPS independently, CSRF refresh async
        startGps();
        scheduleNextPublish(0, "interval");

        refreshCsrfToken();
        checkHealthInBackground();
    }

    window.addEventListener("pagehide", pauseDashboard);
    window.addEventListener("pageshow", function (event) {
        if (event.persisted) resumeDashboard();
    });

    // ============================================================
    // 22. WATCHDOG (F12)
    // ============================================================
    function startWatchdog() {
        if (watchdogTimer) return;
        watchdogTimer = setInterval(function () {
            if (!pageActive || document.hidden) return;
            if (!canSchedule()) return;
            if (scheduleTimer || publishToken) return;
            if (!best || Date.now() - best.ts > AFCON_FRESHNESS_MS) {
                startGps();
                scheduleGpsWait();
            } else {
                startGps();
                scheduleNextPublish(0, "interval");
            }
        }, WATCHDOG_INTERVAL_MS);
    }

    function stopWatchdog() {
        if (watchdogTimer) {
            clearInterval(watchdogTimer);
            watchdogTimer = null;
        }
    }

    // ============================================================
    // 23. HEALTH DIAGNOSTICS (informational only, F7)
    // ============================================================
    function checkHealthInBackground() {
        if (healthInFlight && healthInFlightGen === lifecycleGeneration) {
            return healthInFlight;
        }

        var gen = lifecycleGeneration;
        var token = {};

        healthInFlight = (async function () {
            var controller = new AbortController();
            var t = setTimeout(function () {
                try { controller.abort(); } catch (e) { }
            }, HEALTH_TIMEOUT_MS);

            try {
                var resp = await fetch(HEALTH_CHECK_URL, {
                    method: "GET",
                    headers: { "Accept": "application/json" },
                    credentials: "same-origin",
                    cache: "no-store",
                    signal: controller.signal
                });

                var data = null;
                try { data = await resp.json(); } catch (e) { }

                if (gen !== lifecycleGeneration) return;

                health.dependencies = (data && typeof data === "object" && data.dependencies) || {};

                if (resp.status >= 200 && resp.status < 300) {
                    var keys = Object.keys(health.dependencies);
                    var anyBad = false;
                    for (var i = 0; i < keys.length; i++) {
                        if (health.dependencies[keys[i]] !== "ok") {
                            anyBad = true;
                            break;
                        }
                    }
                    health.status = anyBad ? "degraded" : "ok";
                } else if (resp.status >= 500) {
                    health.status = "server-error";
                } else {
                    health.status = "application-error";
                }
            } catch (e) {
                if (gen === lifecycleGeneration) {
                    health.status = "unreachable";
                }
            } finally {
                clearTimeout(t);
                if (gen === lifecycleGeneration) {
                    health.lastCheck = Date.now();
                    renderAvailabilityBadge(); // F4: update health indicator
                }
                if (healthInFlightToken === token) {
                    healthInFlightToken = null;
                    healthInFlight = null;
                    healthInFlightGen = -1;
                }
            }
        })();

        healthInFlightGen = gen;
        healthInFlightToken = token;
        return healthInFlight;
    }

    // ============================================================
    // 24. SHARED HELPERS FOR CONSOLIDATED INLINE SCRIPTS
    // ============================================================
    function flashMsg(msg, ok) {
        var box = document.createElement('div');
        box.className = 'alert alert-' + (ok ? 'green' : 'red');
        box.style.margin = '0 16px 16px';

        var icon = document.createElement('i');
        icon.className = 'fa-solid fa-' + (ok ? 'circle-check' : 'circle-exclamation');

        var span = document.createElement('span');
        span.style.flex = '1';
        span.textContent = msg;   // XSS-safe; was innerHTML

        var close = document.createElement('button');
        close.type = 'button';
        close.className = 'alert-close';
        close.innerHTML = '<i class="fa-solid fa-xmark"></i>';
        close.addEventListener('click', function () { box.remove(); });

        box.appendChild(icon);
        box.appendChild(span);
        box.appendChild(close);

        var main = document.querySelector('.t-content');
        if (main) main.prepend(box);
    }

    function request(url, body) {
        var controller = new AbortController();
        var t = setTimeout(function () { controller.abort(); }, 20000);
        var gen = lifecycleGeneration;

        return afconPostWithCsrfRetry(
            url,
            function () { return body || {}; },
            controller.signal,
            gen
        ).then(function (result) {
            clearTimeout(t);
            if (result.status >= 200 && result.status < 300) {
                var data = (result.data && typeof result.data === 'object') ? result.data : {};
                // Normalize: every 2xx is a success unless the backend
                // explicitly says otherwise. Without this, a backend that
                // returns {is_online:true} or {declined:true} with no
                // `success` key was treated as a failure by every caller.
                if (data.success === undefined) {
                    data = Object.assign({}, data, { success: true });
                }
                return data;
            }
            // Propagate structured error to the caller, preserving any
            // extra fields the backend sent (e.g. go_live.ready) — only
            // success/status/error/code are normalized on top.
            var err = (result.data && typeof result.data === 'object') ? result.data : {};
            return Object.assign({}, err, {
                success: false,
                status: result.status,
                error: err.error || err.message || ('Request failed (' + result.status + ')'),
                code: err.code || null
            });
        }).catch(function (e) {
            clearTimeout(t);
            throw e;
        });
    }

    function updateOnlineBadge(label) {
        // Accepts a label string ('Online', 'Offline', 'Pending').
        // Callers already pass strings; the old boolean-coercion signature
        // treated every non-empty string as true, so "Offline"/"Pending"
        // both rendered as "Online".
        document.querySelectorAll('[data-online-label]').forEach(function (l) {
            l.textContent = label;
        });
    }

    function refreshPanel(panelName) {
        // No backend fragment endpoint exists yet. Full reload is correct
        // and safe; a follow-up sprint will add /api/.../dashboard/<panel>.
        // Delayed briefly so a flashMsg() shown just before this call has
        // time to render before the page unloads — immediate reload meant
        // every success toast (offer accept/decline, trip actions, cash
        // receipt, vehicle switch) was invisible. Guarded against the
        // double call every handler makes (e.g. refreshPanel('home');
        // refreshPanel('trips');) scheduling two reloads.
        if (refreshPanel._scheduled) return;
        refreshPanel._scheduled = true;
        setTimeout(function () {
            window.location.reload();
        }, 600);
    }

    // Expose for driver_offer_poll.js (F1 migration)
    window.refreshPanel = refreshPanel;

    // ============================================================
    // 25. CONSOLIDATED FEATURE SETUP FUNCTIONS
    // ============================================================

    // 25.1 Alert Sound Picker (from lines 1147-1250)
    function setupAlertSound() {
        var KEY = 'ck_alert_sound';
        function current() {
            try {
                var v = localStorage.getItem(KEY);
                if (v === 'chime' || v === 'urgent' || v === 'bell' || v === 'horn' || v === 'custom') return v;
            } catch (e) {}
            return 'chime';
        }
        var MAX_CUSTOM_BYTES = 5 * 1024 * 1024;
        function customRow() { return document.getElementById('customSoundRow'); }
        function customStatus() { return document.getElementById('customSoundStatus'); }
        function refreshCustomRow(sel) {
            var row = customRow();
            if (row) row.style.display = (sel === 'custom') ? 'block' : 'none';
            var st = customStatus();
            if (st && window.AFCONDriverSound) {
                if (sel !== 'custom') {
                    st.textContent = '';
                } else if (window.AFCONDriverSound.customReady()) {
                    st.textContent = 'Saved on this phone.';
                    window.AFCONDriverSound.customName(function (name) {
                        var el = document.getElementById('customSoundStatus');
                        if (el && name) el.textContent = 'Saved on this phone: ' + name;
                    });
                } else if (window.AFCONDriverSound.customState &&
                           window.AFCONDriverSound.customState() === 'unknown') {
                    st.textContent = 'Loading your sound…';
                } else {
                    st.textContent = 'No file saved yet — choose one below.';
                }
            }
        }
        var checked = current();
        document.querySelectorAll('input[name="alert_sound"]').forEach(function (r) {
            r.checked = (r.value === checked);
            r.addEventListener('change', function () {
                try { localStorage.setItem(KEY, r.value); } catch (e) {}
                refreshCustomRow(r.value);
            });
        });
        refreshCustomRow(checked);
        var fileInput = document.getElementById('customSoundFile');
        if (fileInput) fileInput.addEventListener('change', function () {
            var st = customStatus();
            var f = fileInput.files && fileInput.files[0];
            if (!f) return;
            if (f.size > MAX_CUSTOM_BYTES) {
                if (st) st.textContent = 'File too large (max 5 MB).';
                fileInput.value = '';
                return;
            }
            var rd = new FileReader();
            rd.onload = function () {
                if (st) st.textContent = 'Preparing sound…';
                if (window.AFCONDriverSound && window.AFCONDriverSound.prepareCustom) {
                    window.AFCONDriverSound.prepareCustom(rd.result, f.name, function (ok) {
                        if (st) st.textContent = ok ? 'Saved on this phone.' : 'That file would not play — try another.';
                        if (ok) {
                            try { localStorage.setItem(KEY, 'custom'); } catch (e) {}
                            document.querySelectorAll('input[name="alert_sound"]').forEach(function (r) {
                                r.checked = (r.value === 'custom');
                            });
                            window.AFCONDriverSound.preview('custom');
                        }
                    });
                }
            };
            rd.onerror = function () {
                if (st) st.textContent = 'Could not read that file.';
            };
            try { rd.readAsArrayBuffer(f); } catch (e) {
                if (st) st.textContent = 'Could not read that file.';
            }
        });
        var rmBtn = document.getElementById('customSoundRemove');
        if (rmBtn) rmBtn.addEventListener('click', function () {
            var st = customStatus();
            if (window.AFCONDriverSound) {
                window.AFCONDriverSound.clearCustom(function () {
                    if (st) st.textContent = 'Removed. Chime will play instead.';
                });
            }
            try { localStorage.setItem(KEY, 'chime'); } catch (e) {}
            document.querySelectorAll('input[name="alert_sound"]').forEach(function (r) {
                r.checked = (r.value === 'chime');
            });
            refreshCustomRow('chime');
        });
        var prev = document.getElementById('alertSoundPreview');
        if (prev) prev.addEventListener('click', function () {
            var sel = document.querySelector('input[name="alert_sound"]:checked');
            var name = sel ? sel.value : current();
            try { localStorage.setItem(KEY, name); } catch (e) {}
            if (window.AFCONDriverSound) window.AFCONDriverSound.preview(name);
        });
    }

    // 25.2 Panel Switching (from lines 1326-1355)
    function setupPanelSwitching() {
        document.documentElement.classList.add('ck-js');

        function switchView(name) {
            if (!name) return;
            document.querySelectorAll('.ck-panel').forEach(function (p) {
                p.classList.toggle('ck-active', p.dataset.panel === name);
            });
            document.querySelectorAll('.ck-pane .ck-pane-item[data-ck-nav]').forEach(function (b) {
                b.classList.toggle('active', b.dataset.ckNav === name);
            });
            document.querySelectorAll('.ck-dock .ck-tab[data-ck-nav]').forEach(function (b) {
                b.classList.toggle('ck-active', b.dataset.ckNav === name);
            });
        }
        window.__ckSwitchView = switchView;

        document.querySelectorAll('[data-ck-nav]').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                switchView(btn.dataset.ckNav);
                window.scrollTo({top: 0, behavior: 'smooth'});
            });
        });

        switchView('home');
    }

    // 25.3 Availability Toggle (from lines 1357-1410)
    function setupAvailabilityToggle() {
        document.querySelectorAll('[data-online-toggle]').forEach(function (toggle) {
            toggle.addEventListener('change', function () {
                var online = this.checked;
                updateOnlineBadge(online ? 'Pending' : 'Offline');
                var url = this.getAttribute('data-url');
                if (!url) {
                    document.querySelectorAll('[data-online-toggle]').forEach(function (t) { t.checked = !online; });
                    return;
                }
                request(url, {is_online: online}).then(function (d) {
                    if (!d.success) {
                        document.querySelectorAll('[data-online-toggle]').forEach(function (t) { t.checked = !online; });
                        updateOnlineBadge(!online ? 'Online' : 'Offline');
                        var msg = d.error || 'Could not update availability';
                        if (d.go_live && d.go_live.ready === false) {
                            msg = 'Complete the go-live requirements before going online';
                        }
                        flashMsg(msg, false);
                    } else {
                        updateOnlineBadge(online ? 'Online' : 'Offline');
                        // Mirror the confirmed state to every toggle on the
                        // page (e.g. header + settings panel) — only the one
                        // the driver clicked is guaranteed correct otherwise,
                        // and syncOnline() reads whichever toggle is first.
                        document.querySelectorAll('[data-online-toggle]').forEach(function (t) { t.checked = online; });
                        if (online) {
                            // F1: Explicit user intent clears pause, schedules publish
                            publishingPaused = false;
                            publishPauseReason = null;
                            resetBackoff();
                            startGps();
                            scheduleNextPublish(0, "interval");
                            // refreshPanel() now delays internally (see its
                            // definition), so no separate setTimeout needed.
                            refreshPanel('home');
                            refreshPanel('trips');
                        } else {
                            // NEW (C2): going offline — stop GPS and publishing
                            stopPublishing();
                            stopGpsWatcher();
                            setGpsStatus("Driver switched offline.", false);
                            setPublishStatus("Driver switched offline.", false);
                            renderAvailabilityBadge();
                        }
                    }
                }).catch(function () {
                    document.querySelectorAll('[data-online-toggle]').forEach(function (t) { t.checked = !online; });
                    updateOnlineBadge(!online ? 'Online' : 'Offline');
                    flashMsg('Could not update availability — check your connection', false);
                });
            });
        });
    }

    // 25.4 Go Online CTA (from lines 1402-1410)
    function setupGoOnlineCTA() {
        document.querySelectorAll('.go-online-cta').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var t = document.querySelector('[data-online-toggle]');
                if (!t) return;
                t.checked = true;
                t.dispatchEvent(new Event('change'));
            });
        });
    }

    // 25.5 Offer Actions (from lines 1412-1458)
    function setupOfferActions() {
        document.querySelectorAll('.offer-accept').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                if (!confirm('Accept this ride offer?')) return;
                var prev = this.innerHTML;
                this.disabled = true;
                this.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
                try {
                    var r = await request(this.dataset.url, {});
                    if (r.success) {
                        flashMsg('Offer accepted — trip assigned to you', true);
                        refreshPanel('home');
                        refreshPanel('trips');
                    } else {
                        flashMsg(r.error || 'Could not accept offer', false);
                        this.disabled = false;
                        this.innerHTML = prev;
                    }
                } catch (e) {
                    this.disabled = false;
                    this.innerHTML = prev;
                    flashMsg('Offer store unavailable — try again', false);
                }
            });
        });
        document.querySelectorAll('.offer-decline').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                this.disabled = true;
                var previous = this.innerHTML;
                try {
                    var response = await request(this.dataset.url, {});
                    // request() returns the server body flat, not wrapped in .data
                    if (!response.success || (response.data && response.data.declined === false)) {
                        flashMsg((response && response.error) || 'This offer is no longer active', false);
                        this.disabled = false;
                        this.innerHTML = previous;
                        return;
                    }
                    flashMsg('Offer declined', true);
                    refreshPanel('home');
                    refreshPanel('trips');
                } catch (e) {
                    this.disabled = false;
                    this.innerHTML = previous;
                    flashMsg('Offer service unavailable — try again', false);
                }
            });
        });
    }

    // 25.6 Trip Actions (from lines 1460-1488)
    function setupTripActions() {
        document.querySelectorAll('.trip-action').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                var action = this.dataset.action;
                var labels = {
                    en_route: 'mark en route',
                    arrive: 'mark arrived',
                    start: 'start this trip',
                    complete: 'complete this trip',
                    no_show: 'record the rider as a no-show',
                    cancel: 'cancel this trip'
                };
                var prompt = action === 'no_show'
                    ? 'Confirm the rider did not show up after the 15-minute grace period? A no-show fee will be recorded.'
                    : action === 'cancel'
                        ? 'Cancel this trip? The rider will be notified and asked to search again. No fee is charged.'
                        : 'Confirm to ' + (labels[action] || action) + '?';
                if (!confirm(prompt)) return;
                var prev = this.innerHTML;
                this.disabled = true;
                this.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
                try {
                    var r = await request(this.dataset.url, {action: action});
                    if (r.success) {
                        flashMsg(action === 'cancel' ? 'Trip cancelled — the rider has been asked to search again' : 'Trip updated', true);
                        refreshPanel('trips');
                        refreshPanel('home');
                    } else {
                        flashMsg(r.error || 'Could not update trip', false);
                        this.disabled = false;
                        this.innerHTML = prev;
                    }
                } catch (e) {
                    this.disabled = false;
                    this.innerHTML = prev;
                    flashMsg('Could not update trip', false);
                }
            });
        });
    }

    // 25.7 Cash Receipt (from lines 1490-1518)
    function setupCashReceipt() {
        document.querySelectorAll('.trip-payment-confirm').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                if (!confirm('Confirm that you received the full cash fare from the rider? This records payment as received.')) return;
                var previous = this.innerHTML;
                this.disabled = true;
                this.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Recording receipt…';
                try {
                    var response = await request(this.dataset.url, {});
                    if (response.success) {
                        flashMsg('Cash receipt recorded. Trip remains completed.', true);
                        refreshPanel('trips');
                    } else {
                        flashMsg((response && response.error) || 'Could not record cash receipt', false);
                        this.disabled = false;
                        this.innerHTML = previous;
                    }
                } catch (e) {
                    this.disabled = false;
                    this.innerHTML = previous;
                    flashMsg('Could not record cash receipt — check your connection and retry', false);
                }
            });
        });
    }

    // 25.8 Vehicle Switch (from lines 1520-1545)
    function setupVehicleSwitch() {
        document.querySelectorAll('.vehicle-switch').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                if (!confirm('Switch your active vehicle to ' + this.dataset.plate + '?')) return;
                var prev = this.innerHTML;
                this.disabled = true;
                this.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
                try {
                    var r = await request(this.dataset.url, {
                        vehicle_id: Number(this.dataset.vehicleId),
                        reason: 'shift_start'
                    });
                    if (r.success) {
                        flashMsg('Vehicle switched — assignment history updated', true);
                        refreshPanel('assignments');
                        refreshPanel('vehicles');
                    } else {
                        flashMsg(r.error || 'Could not switch vehicle', false);
                        this.disabled = false;
                        this.innerHTML = prev;
                    }
                } catch (e) {
                    this.disabled = false;
                    this.innerHTML = prev;
                    flashMsg('Could not switch vehicle', false);
                }
            });
        });
    }

    // 25.9 Edit Vehicle (from lines 1547-1553) - keep navigation
    function setupEditVehicle() {
        document.querySelectorAll('.edit-vehicle').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var vehicleId = this.dataset.vehicleId;
                window.location.href = '/transport/vehicles/' + vehicleId + '/edit';
            });
        });
    }

    // ============================================================
    // 26. INITIALIZATION (F13, F14)
    // ============================================================
    (async function initDashboard() {
        // F14: Initialization guard using dataset on root element
        if (root.dataset.dashboardInitialized === "1") return;
        root.dataset.dashboardInitialized = "1";

        try {
            // C1: Wire UI handlers first — panels, toggles, buttons must work offline.
            setupAlertSound();
            setupPanelSwitching();
            setupAvailabilityToggle();
            setupGoOnlineCTA();
            setupOfferActions();
            setupTripActions();
            setupCashReceipt();
            setupVehicleSwitch();
            setupEditVehicle();

            seedLastKnown();
            startWatchdog();

            if (!syncOnline()) {
                setGpsStatus("Offline — GPS paused.", false);
                setPublishStatus("Offline — publishing paused.", false);
                setNetStatus("Offline", true);
                setLocBadge("Offline — publishing paused.", false);
                return;
            }

            startGps();
            scheduleNextPublish(0, "interval");
            refreshCsrfToken();
            checkHealthInBackground();

        } catch (err) {
            console.error("[AFCON] Dashboard initialization failed:", err);
            if (pageActive) {
                setLocBadge("Dashboard initialization failed. Please refresh.", true);
            }
        }
    })();

    // ============================================================
    // 27. END OF AFCON360 DRIVER DASHBOARD v2.5.2
    // ============================================================
})();