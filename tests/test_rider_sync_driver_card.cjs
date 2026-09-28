"use strict";
// Deterministic tests for the rider post-handoff driver card (F-NEW-D).
// Runs under plain node (no deps): `node tests/test_rider_sync_driver_card.cjs`.
//
// Covers: driver_display payload renders the identity card without reload;
// skipped when the server already rendered the card; cleared when the
// payload carries no driver; no internal ids ever reach the DOM.
//
// The module executes on require, so browser globals are stubbed BEFORE
// each require (fresh module per scenario via cache busting).

const path = require("path");
const SYNC = path.join(__dirname, "..", "static", "js", "modules", "transport", "rider_status_sync.js");

let failures = 0;
function check(name, cond, extra) {
    if (cond) { console.log("ok   " + name); }
    else { failures++; console.log("FAIL " + name + (extra ? " :: " + extra : "")); }
}
const flush = async (n) => { for (let i = 0; i < (n || 12); i++) await new Promise((r) => setImmediate(r)); };

const DISPLAY = {
    name: "Ama Serwaa",
    phone: "+233200000001",
    rating: 4.5,
    vehicle: { make: "Toyota", model: "Corolla", license_plate: "GR-1", vehicle_class: "comfort" },
};
function bookingPayload(status, display) {
    return {
        data: {
            booking: {
                booking_reference: "TR-TEST-1",
                status, payment_status: "pending",
                created_at: "2026-09-27T10:00:00+00:00",
                confirmed_at: "2026-09-27T10:01:00+00:00",
                driver_assigned_at: "2026-09-27T10:02:00+00:00",
                driver_en_route_at: null, driver_arrived_at: null,
                pickup_actual_time: null, completed_at: null,
                cancelled_at: null,
            },
            driver_display: display === undefined ? DISPLAY : display,
        },
    };
}

// --- stub environment --------------------------------------------------------
function makeEnv({ serverCard, serverMap, initialStatus, payloads, noTrackLib }) {
    const calls = { fetch: 0, track: [] };
    const queue = (payloads || []).slice();
    const timeouts = [];
    const mount = { innerHTML: "" };
    const trackMount = {
        innerHTML: "",
        getAttribute: (k) => (k === "data-tile-url" ? "https://tiles.example.test/{z}/{x}/{y}.png" :
            k === "data-tile-attr" ? "Example" : null),
    };
    const els = {
        riderStatusSync: {
            getAttribute: (k) => (k === "data-status-url" ? "/api/transport/bookings/REF" :
                k === "data-initial-status" ? initialStatus : null),
        },
        riderStatusBadge: { className: "", textContent: "", setAttribute: () => {} },
        riderPaymentBadge: { className: "", textContent: "", setAttribute: () => {}, getAttribute: () => "" },
        riderProgress: { querySelectorAll: () => [] },
        riderStatusTrail: { querySelectorAll: () => [] },
        riderTimeline: { querySelector: () => null },
        riderMatching: null,
        riderDriverMount: mount,
        riderTrackingMount: trackMount,
    };
    global.document = {
        getElementById: (id) => {
            if (id === "riderMap" && serverMap) return { present: true };
            return els[id] || null;
        },
        querySelector: (sel) => {
            if (sel === ".driver-focus" && serverCard) return { present: true };
            if (sel === "#riderMap" && serverMap) return { present: true };
            return null;
        },
        createElement: () => ({ innerHTML: "", textContent: "", className: "" }),
    };
    const listeners = {};
    global.window = {
        addEventListener: (ev, fn) => { listeners[ev] = fn; },
        dispatchEvent: () => {},
        AFCONTrackDriver: noTrackLib ? undefined : function (ref, label) {
            calls.track.push({ ref, label });
        },
    };
    global.fetch = () => {
        calls.fetch++;
        const next = queue.length ? queue.shift() : queue.default;
        return Promise.resolve({ ok: true, json: () => Promise.resolve(next) });
    };
    global.setTimeout = (fn) => { timeouts.push(fn); fn._stub = true; return 0; };
    global.clearTimeout = () => {};
    global.AbortController = global.AbortController || class {
        constructor() { this.signal = {}; }
        abort() {}
    };
    return { calls, mount, trackMount, listeners, timeouts };
}

function loadFresh() {
    delete require.cache[require.resolve(SYNC)];
    require(SYNC);
}

async function stepTimers(env, n) {
    for (let i = 0; i < n; i++) {
        const fn = env.timeouts.shift();
        if (!fn) break;
        fn();
        await flush(10);
    }
}

(async () => {
    // 1. Card renders from the payload without reload, no internal ids.
    let env = makeEnv({
        serverCard: false, initialStatus: "assigned",
        payloads: [bookingPayload("assigned")],
    });
    loadFresh();
    await flush(20);
    check("card-renders-name", env.mount.innerHTML.includes("Ama Serwaa"), env.mount.innerHTML.slice(0, 120));
    check("card-renders-plate", env.mount.innerHTML.includes("GR-1"), "");
    check("card-renders-call", env.mount.innerHTML.includes("tel:+233200000001"), "");
    check("card-no-ids", !/user_id|driver_id|vehicle_id|license_number/i.test(env.mount.innerHTML), "");
})()
.then(async () => {
    // 1b. Markup in the payload is escaped, never injected.
    const env = makeEnv({
        serverCard: false, initialStatus: "assigned",
        payloads: [bookingPayload("assigned", Object.assign({}, DISPLAY, {
            name: "<script>alert(1)</script>",
        }))],
    });
    loadFresh();
    await flush(20);
    check("card-escapes-html", env.mount.innerHTML.includes("&lt;script&gt;") &&
        !env.mount.innerHTML.includes("<script>alert"), env.mount.innerHTML.slice(0, 200));
})
.then(async () => {
    // 2. Skipped when the server already rendered the card.
    const env = makeEnv({
        serverCard: true, initialStatus: "assigned",
        payloads: [bookingPayload("assigned")],
    });
    loadFresh();
    await flush(20);
    check("card-skipped-when-server-rendered", env.mount.innerHTML === "", JSON.stringify(env.mount.innerHTML));
})
.then(async () => {
    // 3. Cleared when the payload carries no driver.
    const env = makeEnv({
        serverCard: false, initialStatus: "assigned",
        payloads: [bookingPayload("assigned", null)],
    });
    loadFresh();
    await flush(20);
    check("card-empty-without-driver", env.mount.innerHTML === "", JSON.stringify(env.mount.innerHTML));
})
.then(async () => {
    // 4. Handoff path: matching module event also reaches a started loop.
    const env = makeEnv({
        serverCard: false, initialStatus: "confirmed",
        payloads: [bookingPayload("assigned")],
    });
    loadFresh();
    await flush(20);
    const before = env.calls.fetch;
    env.listeners["afcon:ride-status-handoff"] &&
        env.listeners["afcon:ride-status-handoff"]({ detail: { status: "assigned" } });
    await flush(20);
    check("card-renders-after-handoff", env.mount.innerHTML.includes("Ama Serwaa"), "");
    check("handoff-starts-polling", env.calls.fetch > before, `${before}->${env.calls.fetch}`);
})
.then(async () => {
    // 5. Tracking mounts post-handoff: card, map node, Track anchor,
    //    shared bootstrap invoked with ref + name. No internal ids.
    const env = makeEnv({
        serverCard: false, serverMap: false, initialStatus: "assigned",
        payloads: [bookingPayload("assigned")],
    });
    loadFresh();
    await flush(20);
    check("track-card-mounted", env.trackMount.innerHTML.includes('id="riderMap"'), env.trackMount.innerHTML.slice(0, 120));
    check("track-anchor", env.trackMount.innerHTML.includes("Track Driver"), "");
    check("track-bootstrap", env.calls.track.length === 1 &&
        env.calls.track[0].ref === "TR-TEST-1" &&
        env.calls.track[0].label === "Ama Serwaa", JSON.stringify(env.calls.track));
    check("track-no-ids", !/user_id|driver_id|vehicle_id/i.test(env.trackMount.innerHTML), "");
})
.then(async () => {
    // 6. Skipped when the server already rendered tracking.
    const env = makeEnv({
        serverCard: false, serverMap: true, initialStatus: "assigned",
        payloads: [bookingPayload("assigned")],
    });
    loadFresh();
    await flush(20);
    check("track-skipped-when-server-rendered", env.trackMount.innerHTML === "" && env.calls.track.length === 0,
        env.trackMount.innerHTML.slice(0, 120));
})
.then(async () => {
    // 7. Cleared when the trip leaves trackable states (start/end).
    const env = makeEnv({
        serverCard: false, serverMap: false, initialStatus: "assigned",
        payloads: [bookingPayload("assigned"), bookingPayload("in_progress")],
    });
    loadFresh();
    await flush(20);
    check("track-mounted-while-assigned", env.trackMount.innerHTML.includes('id="riderMap"'), "");
    // Second poll sees in_progress -> mount cleared, no re-bootstrap.
    const trackCalls = env.calls.track.length;
    await stepTimers(env, 3);
    await flush(20);
    check("track-cleared-after-start", env.trackMount.innerHTML === "" && env.calls.track.length === trackCalls,
        env.trackMount.innerHTML.slice(0, 120));
})
.then(async () => {
    // 8. Truthful absence when the bootstrap library is unavailable.
    const env = makeEnv({
        serverCard: false, serverMap: false, initialStatus: "assigned",
        payloads: [bookingPayload("assigned")], noTrackLib: true,
    });
    loadFresh();
    await flush(20);
    check("track-absent-without-lib", env.trackMount.innerHTML === "" && env.calls.track.length === 0, "");
})
.then(() => {
    console.log(failures === 0 ? "ALL PASS" : failures + " FAILURES");
    if (failures) process.exitCode = 1;
})
.catch((e) => { console.log("HARNESS ERROR " + (e && e.stack || e)); process.exitCode = 1; });
