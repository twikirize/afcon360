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
    var polls = 0;
    var finished = false;

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
        fetch(optionsUrl, {
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

    function enterAssigned() {
        finished = true;
        if (pingEl) pingEl.className = 'rm-step done';
        if (assignedEl) assignedEl.className = 'rm-step done';
        if (availEl) availEl.textContent = 'A driver accepted your ride.';
        if (assignedSub) assignedSub.textContent = 'Loading driver details…';
        setTimeout(function () { window.location.reload(); }, 1500);
    }

    function tick() {
        if (finished) return;
        fetch(statusUrl, {
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json' }
        })
            .then(function (r) { if (!r.ok) throw new Error('status ' + r.status); return r.json(); })
            .then(function (payload) {
                if (finished) return;
                var st = readStatus(payload);
                if (st && !MATCHING[st]) {
                    /* Cancelled: reload immediately so the page reflects it. */
                    if (st === 'cancelled') { finished = true; window.location.reload(); return; }
                    enterAssigned();
                    return;
                }
                polls += 1;
                /* 3.5s while actively matching; slow down after ~7 min. */
                setTimeout(tick, polls < 120 ? 3500 : 10000);
            })
            .catch(function () {
                if (!finished) setTimeout(tick, 5000);
            });
    }

    fetchOptions();
    var optTimer = setInterval(function () {
        if (finished) { clearInterval(optTimer); return; }
        fetchOptions();
    }, 20000);
    tick();
})();
