// --- PWA: service worker ---
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/transport/sw.js', { scope: '/transport/' })
    .catch(err => console.warn('SW registration failed:', err));
}

// --- PWA: install prompt ---
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  window.__deferredInstallPrompt = e;
  const btn = document.getElementById('installAppBtn');
  if (btn) btn.hidden = false;
});

window.addEventListener('appinstalled', () => {
  window.__deferredInstallPrompt = null;
  const btn = document.getElementById('installAppBtn');
  if (btn) btn.hidden = true;
});

// --- PWA: install button ---
(function () {
  var btn = document.getElementById('installAppBtn');
  if (!btn) return;
  btn.addEventListener('click', async function () {
    var deferred = window.__deferredInstallPrompt;
    if (deferred) {
      deferred.prompt();
      try { await deferred.userChoice; } catch (e) { /* prompt dismissed */ }
      window.__deferredInstallPrompt = null;
      btn.hidden = true;
      return;
    }
    var main = document.querySelector('.t-content');
    if (!main) return;
    var toast = document.createElement('div');
    toast.className = 'alert alert-amber';
    toast.style.margin = '0 16px 16px';
    toast.innerHTML = '<i class="fa-solid fa-circle-info"></i>' +
      '<span style="flex:1;">Use your browser menu &rarr; Add to Home Screen</span>' +
      '<button class="alert-close" type="button" aria-label="Close">&times;</button>';
    toast.querySelector('.alert-close').addEventListener('click', function () {
      toast.remove();
    });
    main.prepend(toast);
    setTimeout(function () { toast.remove(); }, 6000);
  });
})();

// Driver workspace live location publishing — vanilla fetch, no framework.
// Only calls the existing endpoint; never a second source of dispatch truth.
(function () {
    "use strict";

    var root = document.getElementById("driverDashboard");
    if (!root) return; // not the driver workspace page

    var driverId = root.getAttribute("data-driver-id");
    var csrf = root.getAttribute("data-csrf") || "";
    var pingInterval = parseInt(root.getAttribute("data-ping-interval") || "120", 10);
    if (!(pingInterval > 0)) pingInterval = 120;
    if (pingInterval > 300) {
        // eslint-disable-next-line no-console
        console.warn("driver.location_ping_interval_seconds exceeds the 300s freshness TTL; clamped to 300.");
        pingInterval = 300;
    }

    var isOnline = root.getAttribute("data-is-online") === "1";
    var locTimer = null;
    var inFlight = false; // POST in flight (publish only)
    var blockedByPermission = false;
    var permWatcherBound = false;
    var watchId = null;   // single geolocation watcher handle (at most one)
    var best = null;      // best genuine current position {lat, lon, acc, ts}
    var lastGeoCode = null; // last acquisition error code (truthful badge)
    var lastTier = null;  // 'none' | 'low' | 'good' (badge transition tracking)

    // Acquisition policy. FRESHNESS_MS is the stale threshold for both
    // replacement (Rule B) and publishing. LOW_ACCURACY_M is a DISPLAY-ONLY
    // tier for the badge — never a filter, never a matchability decision.
    var FRESHNESS_MS = 5 * 60 * 1000;
    var LOW_ACCURACY_M = 100;
    var OPT_FAST = { enableHighAccuracy: false, timeout: 15000, maximumAge: 0 };
    var OPT_REFINE = { enableHighAccuracy: true, timeout: 30000, maximumAge: 0 };

    function httpsBadge() {
        setLocBadge("Location requires HTTPS. Open https://" + location.host, true);
    }

    // Chrome reports PERMISSION_DENIED (code 1) on insecure origins, which
    // masked the real cause. Watch the Permissions API so a re-grant resumes
    // publishing without a manual toggle; the ping timer retries regardless.
    function watchPermissionResume() {
        if (permWatcherBound) return;
        if (!navigator.permissions || !navigator.permissions.query) return;
        navigator.permissions.query({ name: "geolocation" }).then(function (st) {
            permWatcherBound = true;
            st.onchange = function () {
                if (st.state === "granted" || st.state === "prompt") {
                    blockedByPermission = false;
                    setLocBadge("Location permission restored. Resuming.", false);
                    publishLocation();
                }
            };
        }).catch(function () { /* Permissions API unsupported — timer retry covers it */ });
    }

    function headers(json) {
        var h = {};
        if (json) h["Content-Type"] = "application/json";
        if (csrf) h["X-CSRFToken"] = csrf;
        return h;
    }

    async function postJSON(url, body) {
        var resp = await fetch(url, {
            method: "POST",
            headers: headers(true),
            body: JSON.stringify(body || {}),
        });
        var data = null;
        try { data = await resp.json(); } catch (e) { /* non-JSON */ }
        return { status: resp.status, data: data };
    }

    function setLocBadge(msg, isErr) {
        var el = document.getElementById("dcLocBadge");
        if (!el) return;
        el.textContent = msg;
        el.className = isErr ? "dc-toast err" : "dc-toast ok";
    }

    // The availability checkbox is the live truth; the data attribute is the
    // page-load snapshot. Re-read every tick so offline -> online is picked up
    // without a reload.
    function syncOnline() {
        var t = document.querySelector("[data-online-toggle]");
        isOnline = t ? !!t.checked : root.getAttribute("data-is-online") === "1";
        root.setAttribute("data-is-online", isOnline ? "1" : "0");
        return isOnline;
    }

    function stopLocTimer() {
        if (locTimer) { clearInterval(locTimer); locTimer = null; }
        stopWatch(); // no background GPS drain while offline/off-page (single choke point)
    }

    function startLocTimer() {
        stopLocTimer();
        if (!syncOnline()) {
            setLocBadge("Offline — publishing paused.", false);
            return;
        }
        publishLocation();
        locTimer = setInterval(publishLocation, pingInterval * 1000);
    }

    // --- Pure position policy (no DOM; exported for deterministic tests) ---
    function afconValidObservation(lat, lon, acc) {
        return typeof lat === "number" && isFinite(lat) && lat >= -90 && lat <= 90 &&
               typeof lon === "number" && isFinite(lon) && lon >= -180 && lon <= 180 &&
               typeof acc === "number" && isFinite(acc) && acc >= 0;
    }

    // Replacement Rules A–D. Returns true when *candidate* becomes the
    // operational best. Never mutates inputs. Reported browser accuracy is
    // authoritative — never adjusted, never inferred.
    function afconShouldReplaceBest(current, candidate, nowMs) {
        if (!current) return true; // Rule A — no current position
        if (!candidate || !(candidate.ts <= nowMs)) return false; // future-dated: ignore
        if ((nowMs - current.ts) > FRESHNESS_MS) return true; // Rule B — stale current
        if (!(candidate.acc >= 0) || !(current.acc >= 0)) return false;
        if (candidate.acc <= current.acc * 0.80) return true; // Rule C — materially better
        if (candidate.acc <= current.acc * 1.20 && candidate.ts > current.ts) return true; // Rule D
        return false; // retain a good fresh position over a worse one
    }

    function tierOf(b) {
        if (!b) return "none";
        return b.acc > LOW_ACCURACY_M ? "low" : "good";
    }

    // Ingest one genuine browser observation. Returns true when it becomes
    // the operational best. Observations with missing/invalid accuracy are
    // ignored (accuracy must never be fabricated, not even as 0).
    function ingestPosition(pos, nowMs) {
        if (!pos || !pos.coords) return false;
        var now = (typeof nowMs === "number") ? nowMs : Date.now();
        var lat = pos.coords.latitude, lon = pos.coords.longitude, acc = pos.coords.accuracy;
        if (!afconValidObservation(lat, lon, acc)) return false;
        var ts = (typeof pos.timestamp === "number" && pos.timestamp <= now) ? pos.timestamp : now;
        if (afconShouldReplaceBest(best, { lat: lat, lon: lon, acc: acc, ts: ts }, now)) {
            best = { lat: lat, lon: lon, acc: acc, ts: ts };
            var t = tierOf(best);
            if (t !== lastTier) {
                lastTier = t;
                renderAvailabilityBadge();
            }
            return true;
        }
        return false;
    }

    function renderAvailabilityBadge() {
        if (blockedByPermission) {
            setLocBadge(
                "Location permission denied. Re-grant it in the browser — retrying every " +
                pingInterval + "s.",
                true
            );
            return;
        }
        if (!best) {
            setLocBadge(
                "Location unavailable this tick (" + (lastGeoCode || "?") +
                "). Retrying every " + pingInterval + "s.",
                true
            );
            return;
        }
        if (best.acc > LOW_ACCURACY_M) {
            setLocBadge(
                "Location available — low accuracy (±" + Math.round(best.acc) +
                "m). Publishing every " + pingInterval + "s.",
                false
            );
            return;
        }
        setLocBadge(
            "Location available (±" + Math.round(best.acc) +
            "m). Publishing every " + pingInterval + "s.",
            false
        );
    }

    // --- Continuous acquisition (single watcher max, background refinement) ---
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
            // Permission denied: never invent a location, never POST.
            // Stop the watcher so a denied device is not re-polled; the
            // permission watcher + publish timer drive recovery (no prompt spam).
            blockedByPermission = true;
            stopWatch();
            watchPermissionResume();
            renderAvailabilityBadge();
            return;
        }
        // TIMEOUT(2/3)/unknown: this attempt failed, acquisition continues.
        // A genuine best is retained; the badge only changes when empty.
        if (!best) renderAvailabilityBadge();
    }

    function ensureWatch() {
        if (watchId !== null) return;
        if (!navigator.geolocation || !navigator.geolocation.watchPosition) return;
        try {
            watchId = navigator.geolocation.watchPosition(onAcquired, onAcquireError, OPT_REFINE);
        } catch (e) {
            watchId = null;
        }
    }

    function stopWatch() {
        if (watchId !== null) {
            try { navigator.geolocation.clearWatch(watchId); } catch (e) { /* log-only */ }
            watchId = null;
        }
    }

    // Fast first fix without forcing a high-accuracy wait; refinement
    // continues on the watcher either way (unless permission was denied).
    function kickFastFirst() {
        if (!navigator.geolocation || !navigator.geolocation.getCurrentPosition) return;
        if (!syncOnline() || blockedByPermission) return;
        try {
            navigator.geolocation.getCurrentPosition(
                function (pos) { ingestPosition(pos); ensureWatch(); },
                function (err) {
                    if (err && err.code === 1) { onAcquireError(err); return; }
                    onAcquireError(err);
                    ensureWatch();
                },
                OPT_FAST
            );
        } catch (e) {
            ensureWatch();
        }
    }

    async function publishLocation() {
        if (!syncOnline()) {
            setLocBadge("Offline — publishing paused.", false);
            stopLocTimer();
            return;
        }
        if (inFlight) return;
        if (window.isSecureContext === false) {
            // Geolocation is blocked on http:// pages — this is not a
            // permission problem, so the timer must keep running.
            httpsBadge();
            return;
        }
        if (!navigator.geolocation) {
            setLocBadge("Geolocation is not available in this browser.", true);
            stopLocTimer();
            return;
        }
        // Acquisition and publishing are separate: keep refining in the
        // background, then publish the best genuine FRESH position. A stale
        // best is never published; a failed cycle never fabricates one.
        if (!blockedByPermission) kickFastFirst();
        var now = Date.now();
        if (!best || (now - best.ts) > FRESHNESS_MS) {
            renderAvailabilityBadge();
            return;
        }
        inFlight = true;
        try {
            var r = await postJSON(
                "/api/transport/drivers/" + driverId + "/location",
                { latitude: best.lat, longitude: best.lon, accuracy: best.acc }
            );
            if (r.status === 200 && r.data && r.data.success) {
                setLocBadge("Published " + new Date().toLocaleTimeString() + ".", false);
            } else {
                setLocBadge("Publish failed (" + r.status + "). Retrying next tick.", true);
            }
        } catch (e) {
            setLocBadge("Publish error. Retrying next tick.", true);
        } finally {
            inFlight = false;
        }
    }

    document.addEventListener("change", function (e) {
        var el = e.target;
        if (!el || !el.matches || !el.matches("[data-online-toggle]")) return;
        if (syncOnline()) {
            startLocTimer();
        } else {
            stopLocTimer();
            setLocBadge("Offline — publishing paused.", false);
        }
    }, true);

    startLocTimer();
    document.addEventListener("visibilitychange", function () {
        if (!document.hidden && blockedByPermission && syncOnline()) publishLocation();
    });
    window.addEventListener("pagehide", stopLocTimer);

    // Node-test seam (zero browser effect): expose the pure position policy
    // for deterministic tests. `typeof` guard keeps this safe in browsers.
    if (typeof module !== "undefined" && module.exports) {
        module.exports = {
            afconValidObservation: afconValidObservation,
            afconShouldReplaceBest: afconShouldReplaceBest,
            AFCON_FRESHNESS_MS: FRESHNESS_MS,
            AFCON_LOW_ACCURACY_M: LOW_ACCURACY_M
        };
    }
})();
