/* ============================================================ */
/* FS-1c - RIDER BOOKING-STATUS SYNCHRONIZER                    */
/*                                                             */
/* Canonical read: GET #riderStatusSync[data-status-url]       */
/*   -> payload.data.booking -> compare -> update the          */
/* status-driven rider page UI IN PLACE (no location.reload).  */
/*                                                             */
/* Owns ONLY: 4-step progress, status trail, header badge,     */
/* timeline, payment badge, matching-panel retirement.         */
/*                                                             */
/* Truthfulness contract:                                      */
/*  - state comes from server status + timestamps only;        */
/*    elapsed time / poll counts / client timers NEVER         */
/*    decide a state (cadence controls request frequency only) */
/*  - transient failure keeps the last truthful rendered state */
/*  - terminal status (server STATUS_TRANSITIONS: completed,   */
/*    cancelled, no_show) stops the loop                       */
/*                                                             */
/* Exactly one canonical status loop per page: while the       */
/* booking is matching, rider_matching.js polls and this       */
/* module stays dormant until its handoff event fires.         */
/* ============================================================ */
(function () {
    'use strict';

    var mount = document.getElementById('riderStatusSync');
    if (!mount) return;
    var statusUrl = mount.getAttribute('data-status-url');
    if (!statusUrl) return;

    /* Mirrors templates/transport/rides/show.html server rendering. */
    var STEPS = ['draft', 'pending_payment', 'confirmed', 'assigned',
        'driver_en_route', 'pickup_arrived', 'in_progress', 'completed'];
    /* app/transport/routes.py _MATCHING_STATUSES */
    var MATCHING = { pending_payment: true, confirmed: true };
    /* app/transport/services/booking_service.py STATUS_TRANSITIONS (out == []) */
    var TERMINAL = { completed: true, cancelled: true, no_show: true };
    /* show.html badge class map `sc` (unknown -> pay-pill-pending) */
    var BADGE_CLASS = {
        completed: 'pay-pill-paid',
        in_progress: 'pay-pill-pending',
        assigned: 'pay-pill-pending',
        driver_en_route: 'pay-pill-pending',
        pickup_arrived: 'pay-pill-pending',
        confirmed: 'pay-pill-pending',
        cancelled: 'pay-pill-fail',
        pending_payment: 'pay-pill-pending',
        no_show: 'pay-pill-fail',
        disputed: 'pay-pill-fail'
    };

    /* Bounded polling contract (repo patterns: 3.5s-30s intervals,
     * AbortController timeout in show.html cancelRide). */
    var POLL_MS = 5000;
    var BACKOFF_MS = [5000, 10000, 15000];
    var REQ_TIMEOUT_MS = 15000;

    var badgeEl = document.getElementById('riderStatusBadge');
    var payBadgeEl = document.getElementById('riderPaymentBadge');
    var progressEl = document.getElementById('riderProgress');
    var trailEl = document.getElementById('riderStatusTrail');
    var timelineEl = document.getElementById('riderTimeline');
    var matchingEl = document.getElementById('riderMatching');

    function titleCase(v) {
        return String(v || '').split('_').map(function (w) {
            return w ? w.charAt(0).toUpperCase() + w.slice(1) : w;
        }).join(' ');
    }

    /* Observed server rendering: booking.* are already-serialized
     * ISO strings (service dict), so |datetimeformat passes them
     * through unchanged. Display the canonical payload's timestamps
     * verbatim - no client-side reformatting - so an unchanged
     * payload matches the rendered DOM exactly (zero rewrite). */
    function tsText(v) {
        return v ? String(v) : '';
    }

    function normStatus(raw) {
        if (raw && typeof raw === 'object') raw = raw.value;
        return String(raw || '').toLowerCase();
    }

    /* show.html line 154 rp_stage mapping. */
    function stageOf(status) {
        if (status === 'draft' || status === 'pending_payment') return 0;
        if (status === 'confirmed' || status === 'assigned') return 1;
        if (status === 'driver_en_route' || status === 'pickup_arrived') return 2;
        if (status === 'in_progress' || status === 'completed') return 3;
        return 0;
    }

    function applyProgress(status) {
        if (!progressEl) return;
        var stage = stageOf(status);
        var steps = progressEl.querySelectorAll('.rp-step');
        for (var i = 0; i < steps.length; i++) {
            var cls = 'rp-step';
            if (i < stage) cls += ' done';
            else if (i === stage) cls += ' active';
            steps[i].className = cls;
            var dot = steps[i].querySelector('.rp-dot');
            if (dot) {
                var done = (i === steps.length - 1)
                    ? status === 'completed' : i < stage;
                dot.textContent = done ? '\u2713' : String(i + 1);
            }
            var line = steps[i].querySelector('.rp-line');
            if (line) line.className = 'rp-line' + (i < stage ? ' done' : '');
        }
    }

    /* show.html line 166 sf-step mapping (done/active/skip-if-cancelled). */
    function applyTrail(status) {
        if (!trailEl) return;
        var curIdx = STEPS.indexOf(status);
        if (curIdx < 0) curIdx = 0;
        var sf = trailEl.querySelectorAll('.sf-step');
        for (var i = 0; i < sf.length; i++) {
            var cls = 'sf-step';
            if (i < curIdx) cls += ' done';
            else if (i === curIdx) cls += ' active';
            else if (status === 'cancelled') cls += ' skip';
            sf[i].className = cls;
        }
    }

    function applyBadge(status) {
        if (!badgeEl) return;
        badgeEl.className = 'badge ' +
            (BADGE_CLASS[status] || 'pay-pill-pending');
        badgeEl.textContent = titleCase(status);
        badgeEl.setAttribute('data-status', status);
    }

    function applyPayment(raw) {
        if (!payBadgeEl) return;
        var v = String(raw || 'pending').toLowerCase();
        payBadgeEl.className = 'badge ' +
            (v === 'captured' ? 'pay-pill-paid' : 'pay-pill-pending');
        payBadgeEl.textContent = titleCase(v);
        payBadgeEl.setAttribute('data-payment-status', v);
    }

    function setRow(key, cls, timeText) {
        if (!timelineEl) return;
        var row = timelineEl.querySelector('[data-tl="' + key + '"]');
        if (!row) return;
        row.className = cls;
        var t = row.querySelector('.tl-time');
        if (t && t.textContent !== timeText) t.textContent = timeText;
    }

    /* show.html lines 302-311 timeline rules, replicated exactly
     * (incl. Trip Started: active when in_progress, done only once
     * completed_at exists). */
    function applyTimeline(status, b) {
        if (!timelineEl) return;
        setRow('created', 'tl-step' + (b.created_at ? ' done' : ''),
            tsText(b.created_at));
        setRow('confirmed',
            'tl-step ' + (b.confirmed_at ? 'done' : 'skip'),
            tsText(b.confirmed_at));
        setRow('assigned',
            'tl-step ' + (b.driver_assigned_at ? 'done' : 'skip'),
            tsText(b.driver_assigned_at));
        setRow('en_route',
            'tl-step ' + (b.driver_en_route_at ? 'done' : 'skip'),
            tsText(b.driver_en_route_at));
        setRow('arrived',
            'tl-step ' + (b.driver_arrived_at ? 'done' : 'skip'),
            tsText(b.driver_arrived_at));
        setRow('started',
            'tl-step ' + (status === 'in_progress' ? 'active'
                : (b.completed_at ? 'done' : 'skip')),
            tsText(b.pickup_actual_time));
        setRow('completed',
            'tl-step ' + (b.completed_at ? 'done' : 'skip'),
            tsText(b.completed_at));
        var cancelRow = timelineEl.querySelector('[data-tl="cancelled"]');
        if (cancelRow) {
            var ct = cancelRow.querySelector('.tl-time');
            if (b.cancelled_at) {
                cancelRow.className = 'tl-step done';
                cancelRow.removeAttribute('hidden');
                if (ct) ct.textContent = tsText(b.cancelled_at);
            } else {
                cancelRow.setAttribute('hidden', '');
                if (ct) ct.textContent = '';
            }
        }
    }

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    /* F-NEW-D: post-handoff driver identity. The server card only exists
     * when the driver was assigned before page load; after a live
     * assignment the rider-safe driver_display payload (same fields the
     * server renders, no internal ids) populates the mount instead. */
    function renderDriverCard(display) {
        var mount = document.getElementById('riderDriverMount');
        if (!mount) return;
        /* Server already rendered the card — nothing to do. */
        if (document.querySelector('.driver-focus')) {
            if (mount.innerHTML !== '') mount.innerHTML = '';
            return;
        }
        if (!display) {
            if (mount.innerHTML !== '') mount.innerHTML = '';
            return;
        }
        var name = display.name || 'Driver';
        var initials = esc(String(name).slice(0, 2).toUpperCase());
        var phone = display.phone || 'Contact via app';
        var rating = (display.rating != null && isFinite(display.rating))
            ? '★ ' + Number(display.rating).toFixed(1) : '★ —';
        var html = '<div class="card ride-card"><div class="card-header">' +
            '<span class="card-title">Your Driver</span></div>' +
            '<div class="driver-focus"><div class="driver-avatar">' +
            initials + '</div><div><div class="driver-name">' + esc(name) +
            '</div><div class="driver-sub">' + esc(phone) + '</div></div>' +
            '<div style="margin-left:auto;text-align:right;">' +
            '<div class="driver-rating">' + esc(rating) + '</div></div></div>';
        if (display.vehicle) {
            var v = display.vehicle;
            var vcls = v.vehicle_class
                ? esc(String(v.vehicle_class).replace(/_/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); })) + ' · '
                : '';
            html += '<div class="driver-focus" style="border-bottom:none;">' +
                '<div style="width:48px;height:48px;background:#F1F5F9;border:1px solid #E2E8F0;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:1.3rem;flex-shrink:0;">🚌</div>' +
                '<div><div class="driver-name">' + esc(v.make || '') + ' ' + esc(v.model || '') + '</div>' +
                '<div class="driver-sub">' + vcls +
                '<span class="plate-badge">' + esc(v.license_plate || '') + '</span></div></div>';
            if (display.phone) {
                html += '<div class="driver-call" style="margin-left:auto;"><a class="call-btn" href="tel:' +
                    esc(display.phone) + '"><i class="fa-solid fa-phone"></i> Call</a></div>';
            }
            html += '</div>';
        }
        html += '</div>';
        if (mount.innerHTML !== html) mount.innerHTML = html;
    }

    /* F-NEW-E: post-handoff tracking surface. The server card (with
     * its map + stream bootstrap) only exists when tracking was allowed
     * at render time. When assignment lands later, mount the same card
     * structure and bootstrap it through the shared AFCONTrackDriver —
     * reusing the page's map/stream components, never a second stack.
     * Truthful degradation: no map without the libraries, no invented
     * location. Cleared when tracking is not allowed for the status. */
    var TRACKABLE = { assigned: true, driver_en_route: true, pickup_arrived: true };
    function renderTracking(display, ref, status) {
        var mount = document.getElementById('riderTrackingMount');
        if (!mount) return;
        /* Server already rendered the card — nothing to do. */
        if (document.getElementById('riderMap')) {
            if (mount.innerHTML !== '') mount.innerHTML = '';
            return;
        }
        if (!display || !TRACKABLE[status] || !ref ||
                typeof window.AFCONTrackDriver !== 'function') {
            if (mount.innerHTML !== '') mount.innerHTML = '';
            return;
        }
        var tileUrl = mount.getAttribute('data-tile-url') || '';
        var tileAttr = mount.getAttribute('data-tile-attr') || '';
        if (!tileUrl) {
            if (mount.innerHTML !== '') mount.innerHTML = '';
            return;
        }
        mount.innerHTML =
            '<div class="card ride-card"><div class="card-header">' +
            '<span class="card-title">Live Tracking</span></div>' +
            '<div class="map-frame"><div id="riderMap" ' +
            'data-geo-map-status="pending"></div>' +
            '<span id="riderLiveState" class="map-status-pill" ' +
            'role="status">Connecting…</span></div>' +
            '<div class="map-updated" id="riderLiveUpdated"></div>' +
            '<div style="padding:0 16px 12px;"><a href="#riderMap" ' +
            'class="btn btn-primary btn-track">' +
            '<i class="fa-solid fa-location-crosshairs"></i> ' +
            'Track Driver</a></div></div>';
        try {
            window.AFCONTrackDriver(ref, display.name || 'Assigned driver',
                tileUrl, tileAttr);
        } catch (e) {
            mount.innerHTML = '';
        }
    }

    function signature(status, payRaw, times, display) {
        return [status, String(payRaw || '').toLowerCase()]
            .concat(times).concat([display ? JSON.stringify(display) : ''])
            .join('|');
    }

    function payloadTimes(b) {
        return [tsText(b.confirmed_at), tsText(b.driver_assigned_at),
            tsText(b.driver_en_route_at), tsText(b.driver_arrived_at),
            tsText(b.pickup_actual_time), tsText(b.completed_at),
            tsText(b.cancelled_at)];
    }

    /* Phase 5: initialize from the DOM/server-rendered state so an
     * unchanged canonical payload causes zero DOM writes. */
    function domTime(key) {
        if (!timelineEl) return '';
        var row = timelineEl.querySelector('[data-tl="' + key + '"]');
        if (!row || row.hasAttribute('hidden')) return '';
        var t = row.querySelector('.tl-time');
        return t ? t.textContent.trim() : '';
    }

    function initialSignature() {
        var status = String(
            mount.getAttribute('data-initial-status') || '').toLowerCase();
        var pay = payBadgeEl
            ? String(payBadgeEl.getAttribute('data-payment-status') || '')
                .toLowerCase()
            : '';
        return signature(status, pay, [domTime('confirmed'),
            domTime('assigned'), domTime('en_route'), domTime('arrived'),
            domTime('started'), domTime('completed'), domTime('cancelled')]);
    }

    var running = false;
    var timer = null;
    var controller = null;
    var errors = 0;
    var lastSig = initialSignature();

    function stop() {
        running = false;
        if (timer) { clearTimeout(timer); timer = null; }
        if (controller) {
            try { controller.abort(); } catch (e) { /* already gone */ }
            controller = null;
        }
    }

    function schedule(ms) {
        if (!running) return;
        if (timer) clearTimeout(timer);
        timer = setTimeout(tick, ms);
    }

    function apply(b, display) {
        var status = normStatus(b.status);
        if (!status) return;
        var sig = signature(status, b.payment_status, payloadTimes(b),
            display);
        if (sig === lastSig) return;
        applyProgress(status);
        applyTrail(status);
        applyBadge(status);
        applyTimeline(status, b);
        applyPayment(b.payment_status);
        renderDriverCard(display || null);
        renderTracking(display || null, b.booking_reference, status);
        if (!MATCHING[status] && matchingEl) matchingEl.hidden = true;
        lastSig = sig;
    }

    function tick() {
        if (!running || controller) return;
        controller = new AbortController();
        var timeout = setTimeout(function () {
            if (controller) controller.abort();
        }, REQ_TIMEOUT_MS);
        fetch(statusUrl, {
            method: 'GET',
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json' },
            signal: controller.signal
        }).then(function (r) {
            if (!r.ok) throw new Error('status ' + r.status);
            return r.json();
        }).then(function (payload) {
            clearTimeout(timeout);
            controller = null;
            if (!running) return;
            errors = 0;
            var b = payload && payload.data && payload.data.booking;
            if (!b) { schedule(POLL_MS); return; }
            apply(b, payload.data.driver_display);
            var status = normStatus(b.status);
            /* Terminality comes from the server status, never from
             * elapsed time or poll count. */
            if (TERMINAL[status]) { stop(); return; }
            /* Booking back in matching: rider_matching.js owns the loop. */
            if (MATCHING[status]) { stop(); return; }
            schedule(POLL_MS);
        }).catch(function () {
            clearTimeout(timeout);
            controller = null;
            if (!running) return;
            /* Transient failure: keep the last truthful state. */
            var delay = BACKOFF_MS[Math.min(errors, BACKOFF_MS.length - 1)];
            errors += 1;
            schedule(delay);
        });
    }

    function start() {
        if (running) return;
        running = true;
        errors = 0;
        tick();
    }

    /* Matching handoff (dispatched by rider_matching.js enterAssigned):
     * its status loop has already ended, so exactly one loop remains. */
    window.addEventListener('afcon:ride-status-handoff', function () {
        start();
    });

    window.addEventListener('pagehide', stop);

    var initialStatus = String(
        mount.getAttribute('data-initial-status') || '').toLowerCase();
    if (!MATCHING[initialStatus] && !TERMINAL[initialStatus]) start();
})();
