/* ============================================================ */
/* BOOKING SHOW - RIDER MATCHING PANEL (post-confirm live search) */
/* Polls booking status; refreshes live availability + fares.    */
/* On assignment flips the panel to "Driver assigned" then       */
/* reloads so the canonical driver/tracking view renders.        */
/* ============================================================ */

(function () {
    'use strict';

    var panel = document.getElementById('riderMatching');
    if (!panel) return;

    var statusUrl = panel.getAttribute('data-status-url');
    var optionsUrl = panel.getAttribute('data-options-url');
    var csrf = panel.getAttribute('data-csrf') || '';
    var availEl = document.getElementById('rmAvail');
    var optsEl = document.getElementById('rmOptions');
    var pingEl = document.getElementById('rmPing');
    var assignedEl = document.getElementById('rmAssigned');
    var assignedSub = document.getElementById('rmAssignedSub');

    /* While status is one of these, the rider is still being matched. */
    var MATCHING = { pending_payment: true, confirmed: true };
    /* Bounded search budget (FS-6b): max MATCHING status polls before the
       panel truthfully admits no driver is coming. At the 3.5s cadence
       below, 60 polls ≈ 3.5 minutes. Named and adjustable; never tied to
       fake availability and never a backend state change. */
    var SEARCH_BUDGET_POLLS = 60;
    var polls = 0;
    var finished = false;
    var noSupply = false;
    var optTimer = null;
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
        if (failures >= 3 && availEl && !finished && !noSupply) {
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

    function optionBody() {
        var body = {
            service_type: panel.getAttribute('data-service-type') || 'on_demand',
            currency: panel.getAttribute('data-currency') || 'USD'
        };
        var pl = panel.getAttribute('data-pickup-lat');
        var pn = panel.getAttribute('data-pickup-lng');
        var dl = panel.getAttribute('data-dropoff-lat');
        var dn = panel.getAttribute('data-dropoff-lng');
        if (pl && pn) { body.pickup_latitude = parseFloat(pl); body.pickup_longitude = parseFloat(pn); }
        if (dl && dn) { body.dropoff_latitude = parseFloat(dl); body.dropoff_longitude = parseFloat(dn); }
        return body;
    }

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function fmtFare(o) {
        var amt = Number(o.fare_total || 0).toFixed(2);
        var cur = o.currency || 'USD';
        return cur === 'USD' ? '$' + amt : amt + ' ' + cur;
    }

    function renderOptions(data) {
        if (finished) return;
        var opts = (data && data.options) || [];
        if (!opts.length) {
            if (availEl) {
                availEl.textContent = 'No vehicles available nearby right now — we keep searching.';
            }
            if (optsEl) optsEl.innerHTML = '';
            return;
        }
        var total = 0;
        opts.forEach(function (o) { total += (o.available_count || 0); });
        if (availEl) {
            availEl.textContent = total + ' vehicle' + (total === 1 ? '' : 's') +
                ' available nearby' +
                (opts[0].eta_minutes != null ? ' · ETA ~' + opts[0].eta_minutes + ' min' : '');
        }
        if (optsEl) {
            optsEl.innerHTML = '';
            opts.slice(0, 3).forEach(function (o) {
                var row = document.createElement('div');
                row.className = 'rm-opt';
                row.innerHTML =
                    '<span>' + esc(o.display_name || o.vehicle_class) +
                    ' <span style="color:var(--text-muted);">\u00d7' +
                    (o.available_count || 0) + '</span></span>' +
                    '<span style="font-weight:600;">' + esc(fmtFare(o)) + '</span>';
                optsEl.appendChild(row);
            });
        }
    }

    function fetchOptions() {
        if (finished || !optionsUrl) return;
        fetchWithTimeout(optionsUrl, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-CSRFToken': csrf,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify(optionBody())
        })
            .then(function (r) { if (!r.ok) throw new Error('options ' + r.status); return r.json(); })
            .then(function (payload) { renderOptions(payload && payload.data); })
            .catch(function () { /* availability is supplementary — poll continues */ });
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

    function enterNoSupply() {
        /* Truthful terminal state: budget exhausted while the booking is
           still genuinely matching. No backend change, no fake driver,
           no new booking — rider-facing polling ends here. */
        finished = true;
        noSupply = true;
        if (optTimer) { clearInterval(optTimer); optTimer = null; }
        if (pingEl) pingEl.className = 'rm-step done';
        if (availEl) availEl.textContent =
            'No drivers available right now. ' +
            'Try again later or choose another transport option.';
        if (optsEl) {
            optsEl.innerHTML = '';
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn btn-secondary rm-retry';
            btn.textContent = 'Try Again';
            btn.addEventListener('click', retrySearch);
            optsEl.appendChild(btn);
        }
    }

    function retrySearch() {
        /* Explicit rider retry against the SAME booking: reset the
           frontend budget and restart the existing pollers. statusUrl
           and optionsUrl are unchanged, so no second booking can result
           and no backend dispatch state is touched. */
        if (!noSupply) return;
        noSupply = false;
        finished = false;
        polls = 0;
        if (pingEl) pingEl.className = 'rm-step active';
        if (availEl) availEl.textContent = 'Checking available vehicles…';
        if (optsEl) optsEl.innerHTML = '';
        fetchOptions();
        startOptionPolling();
        tick();
    }

    function startOptionPolling() {
        stopOptionPolling();
        optTimer = setInterval(function () {
            if (finished) { stopOptionPolling(); return; }
            fetchOptions();
        }, 20000);
    }

    function stopOptionPolling() {
        if (optTimer) { clearInterval(optTimer); optTimer = null; }
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
                    enterAssigned(st);
                    return;
                }
                polls += 1;
                /* Budget is checked only after a confirmed MATCHING read,
                   so a legitimate assignment at the boundary always wins. */
                if (budgetExhausted(polls)) { enterNoSupply(); return; }
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

    fetchOptions();
    startOptionPolling();
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
