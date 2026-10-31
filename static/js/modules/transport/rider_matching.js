/* ============================================================ */
/* BOOKING SHOW - RIDER MATCHING PANEL (post-confirm live search) */
/* Polls only authoritative booking status after fare acceptance. */
/* On assignment flips the panel to "Driver assigned" then       */
/* reloads so the canonical driver/tracking view renders.        */
/* ============================================================ */

(function () {
    'use strict';

    var panel = document.getElementById('riderMatching');
    if (!panel) return;

    var statusUrl = panel.getAttribute('data-status-url');
    var availEl = document.getElementById('rmAvail');
    var retryMountEl = document.getElementById('rmRetryActions');
    var pingEl = document.getElementById('rmPing');
    var assignedEl = document.getElementById('rmAssigned');
    var assignedSub = document.getElementById('rmAssignedSub');

    /* While status is one of these, the rider is still being matched. */
    var MATCHING = { pending_payment: true, confirmed: true };
    /* Bounded search budget (FS-6b): max MATCHING status polls before the
       panel tells the rider the search is taking longer than expected.
       At the 3.5s cadence below, 60 polls = ~3.5 minutes. Named and
       adjustable; never tied to fake availability and never a backend
       state change. UI-16-A: budget exhaustion is NOT a terminal
       verdict — the backend booking may still be genuinely matching. */
    var SEARCH_BUDGET_POLLS = 60;
    var polls = 0;
    var finished = false;
    var searchPaused = false;
    /* Bounded requests (FS-4): AbortController timeout so a stalled
       network retries on cadence instead of hanging a poll forever. */
    var REQ_TIMEOUT_MS = 15000;
    var failures = 0;

    function fetchWithTimeout(url, options) {
        options = options || {};
        var controller;
        try {
            controller = new AbortController();
        } catch (e) {
            return fetch(url, options);
        }
        var timer = setTimeout(function () {
            try { controller.abort(); } catch (e) {}
        }, REQ_TIMEOUT_MS);
        options.signal = controller.signal;
        return fetch(url, options).then(function (r) {
            clearTimeout(timer);
            return r;
        }, function (err) {
            clearTimeout(timer);
            throw err;
        });
    }

    function noteFailure() {
        /* Truthful connectivity note after repeated failures — never a
           no-supply verdict (failures don't spend the search budget). */
        failures += 1;
        if (failures >= 3 && availEl && !finished && !searchPaused) {
            availEl.textContent = 'Connection issue — still trying.';
        }
    }

    function isMatchingStatus(st) {
        return !!MATCHING[st];
    }

    function budgetExhausted(p) {
        return p >= SEARCH_BUDGET_POLLS;
    }

    function readStatus(payload) {
        var b = payload && payload.data && payload.data.booking;
        var s = b && b.status;
        if (s && typeof s === 'object') s = s.value;
        return String(s || '').toLowerCase();
    }

    function enterAssigned(st) {
        finished = true;
        if (pingEl) pingEl.className = 'rm-step done';
        if (assignedEl) assignedEl.className = 'rm-step done';
        if (availEl) availEl.textContent = 'A driver accepted your ride.';
        if (assignedSub) assignedSub.textContent = 'Driver assigned';
        /* FS-1c: hand off to rider_status_sync.js instead of reloading.
           finished=true has already ended this module's status loop, so
           exactly one canonical status poller remains on the page. */
        window.dispatchEvent(new CustomEvent('afcon:ride-status-handoff',
            { detail: { status: st || '' } }));
    }

    function pauseSearchForSlowMatching() {
        /* UI-16-A: in-progress pause, NOT a terminal verdict. The client
           polling budget is exhausted while the backend booking is still
           genuinely matching, so the copy must keep describing an ongoing
           search — never "no drivers available". No backend change, no
           fake driver, no new booking; rider-facing polling pauses here
           until the rider explicitly resumes the same status check. */
        finished = true;
        searchPaused = true;
        if (pingEl) pingEl.className = 'rm-step done';
        if (availEl) availEl.textContent =
            'Still checking for drivers. ' +
            'This is taking longer than expected.';
        if (retryMountEl) {
            retryMountEl.innerHTML = '';
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn btn-secondary rm-retry';
            btn.textContent = 'Keep checking';
            btn.addEventListener('click', retrySearch);
            retryMountEl.appendChild(btn);
        }
    }

    function retrySearch() {
        /* Explicit rider resume of status polling against the SAME
           booking: reset the frontend budget and restart the same status
           check. No new booking or backend dispatch state is created. */
        if (!searchPaused) return;
        searchPaused = false;
        finished = false;
        polls = 0;
        if (pingEl) pingEl.className = 'rm-step active';
        if (availEl) availEl.textContent = 'Checking for driver acceptance…';
        if (retryMountEl) retryMountEl.innerHTML = '';
        tick();
    }

    function tick() {
        if (finished) return;
        fetchWithTimeout(statusUrl, {
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json' }
        })
            .then(function (r) { if (!r.ok) throw new Error('status ' + r.status); return r.json(); })
            .then(function (payload) {
                if (finished) return;
                failures = 0;
                var st = readStatus(payload);
                if (st && !isMatchingStatus(st)) {
                    /* Cancelled: reload immediately so the page reflects it. */
                    if (st === 'cancelled') { finished = true; window.location.reload(); return; }
                    /* MATCH-01-owned: matching failed terminally — reload so
                       the server renders the no_match branch (reason copy +
                       Try again / Adjust request). Never enterAssigned: no
                       driver accepted. */
                    if (st === 'no_match') { finished = true; window.location.reload(); return; }
                    enterAssigned(st);
                    return;
                }
                polls += 1;
                /* Budget is checked only after a confirmed MATCHING read,
                   so a legitimate assignment at the boundary always wins. */
                if (budgetExhausted(polls)) { pauseSearchForSlowMatching(); return; }
                setTimeout(tick, 3500);
            })
            .catch(function () {
                /* Transient failure: retry on the same cadence without
                   spending budget — a network error must never read as
                   "no drivers". The finished guard keeps a terminal
                   state authoritative. */
                if (!finished) { noteFailure(); setTimeout(tick, 5000); }
            });
    }

    tick();

    /* Node-test seam (zero browser effect): expose the pure matching
       policy for deterministic tests. `typeof` guard keeps this safe
       in browsers. */
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            isMatchingStatus: isMatchingStatus,
            budgetExhausted: budgetExhausted,
            SEARCH_BUDGET_POLLS: SEARCH_BUDGET_POLLS
        };
    }
})();
