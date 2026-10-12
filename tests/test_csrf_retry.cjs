"use strict";
// Proof for the driver-dashboard CSRF refresh-and-retry contract.
// Runs under plain node (no deps): `node tests/test_csrf_retry.cjs`.
//
// Parts 1-3 prove the pure helper + the bound (one refresh, one replay).
// Part 4 proves the WIRING: the real publishLocation, driven through the
// timer callback, actually routes its POST through the retry helper.
//
// The dashboard file executes on require, so browser globals are stubbed
// BEFORE the require (fresh module per scenario via cache busting). The
// "driverDashboard" root must be truthy so the IIFE reaches its exports.

const path = require("path");
const DASH = path.join(__dirname, "..", "static", "js", "modules", "transport", "driver-dashboard.js");

let failures = 0;
function check(name, cond, extra) {
    if (cond) { console.log("ok   " + name); }
    else { failures++; console.log("FAIL " + name + (extra ? " :: " + extra : "")); }
}
const flush = async (n) => { for (let i = 0; i < (n || 6); i++) await new Promise((r) => setImmediate(r)); };

function fakeRoot() {
    return {
        getAttribute: (k) => ({
            "data-driver-id": "179", "data-csrf": "csrf-token",
            "data-ping-interval": "120", "data-is-online": "1",
        }[k] || null),
        setAttribute: () => {},
    };
}
function stubGlobals(root, extraDoc) {
    global.window = { isSecureContext: true, addEventListener: () => {} };
    global.location = { host: "192.168.2.214:5443", protocol: "https:" };
    global.document = {
        getElementById: (id) => (id === "driverDashboard" ? root : (extraDoc && extraDoc(id)) || null),
        querySelector: () => null,
        addEventListener: () => {},
    };
}
function reload() {
    delete require.cache[require.resolve(DASH)];
    return require(DASH);
}

// Minimal env (no geolocation): for the pure-predicate + helper tests.
function makeEnv(fetchImpl) {
    stubGlobals(fakeRoot(), null);
    Object.defineProperty(global, "navigator", { value: { geolocation: {} }, configurable: true, writable: true });
    global.fetch = fetchImpl;
    global.setInterval = () => 0;
    global.clearInterval = () => {};
    return reload();
}

// Full env (geolocation + captured timer): drives the real publish flow.
function makeGeoEnv(fetchImpl) {
    const root = fakeRoot();
    const badge = { textContent: "", className: "" };
    const geo = {
        getCalls: [], watchCalls: [], clearCalls: [], watchId: 0,
        oneshotQueue: [], watchOk: null, watchErr: null,
        getCurrentPosition(ok, err) {
            this.getCalls.push({});
            const next = this.oneshotQueue.shift();
            if (next && next.ok) ok(next.pos); else if (next) err(next.err);
        },
        watchPosition(ok, err) { this.watchCalls.push({}); this.watchOk = ok; this.watchErr = err; return ++this.watchId; },
        clearWatch(id) { this.clearCalls.push(id); },
    };
    const intervals = [];
    stubGlobals(root, (id) => (id === "dcLocBadge" ? badge : null));
    Object.defineProperty(global, "navigator", { value: { geolocation: geo }, configurable: true, writable: true });
    global.fetch = fetchImpl;
    global.setInterval = (fn) => { intervals.push(fn); return intervals.length; };
    global.clearInterval = () => {};
    return { geo, intervals, badge, policy: reload() };
}

async function main() {
    // --- Part 1: pure predicate ---------------------------------------------
    const policy = makeEnv(async () => ({ status: 200, json: async () => ({}) }));
    const S = policy.afconShouldRetryAfter400;
    check("predicate-exported", typeof S === "function");
    check("expired-retries", S(400, { code: "csrf_expired" }) === true);
    check("missing-does-not-retry", S(400, { code: "csrf_missing" }) === false);
    check("invalid-does-not-retry", S(400, { code: "csrf_invalid" }) === false);
    check("plain-400-no-retry", S(400, { error: "bad payload" }) === false);
    check("non-400-no-retry", S(200, { code: "csrf_expired" }) === false);
    check("null-body-no-retry", S(400, null) === false);
    check("string-body-parsed", S(400, '{"code":"csrf_expired"}') === true);
    check("garbage-string-no-retry", S(400, "<html>nope") === false);

    // --- Part 2: expired token -> exactly one refresh + one replay ----------
    let calls = [];
    let posts = 0;
    const env = makeEnv(async (url, opts) => {
        calls.push({ url, headers: (opts && opts.headers) || {} });
        if (url === "/api/transport/csrf-token") {
            return { status: 200, json: async () => ({ success: true, csrf_token: "fresh-token" }) };
        }
        posts++;
        if (posts === 1) {
            return { status: 400, json: async () => ({ status: "error", code: "csrf_expired" }) };
        }
        return { status: 200, json: async () => ({ success: true }) };
    });
    await env.afconPostWithCsrfRetry("/api/transport/drivers/179/location", function () {
        return { latitude: 1, longitude: 2, accuracy: 5, client_ts: Date.now() };
    });
    check("expired-does-one-refresh", calls.filter((c) => c.url === "/api/transport/csrf-token").length === 1);
    check("expired-replays-once", posts === 2, String(posts));
    check("replay-uses-refreshed-token", calls[2].headers["X-CSRFToken"] === "fresh-token");
    check("first-attempt-uses-initial-token", calls[0].headers["X-CSRFToken"] === "csrf-token");

    // --- Part 3: missing token -> NO refresh, NO replay ---------------------
    calls = []; posts = 0;
    const env2 = makeEnv(async (url) => {
        calls.push({ url });
        if (url === "/api/transport/csrf-token") {
            return { status: 200, json: async () => ({ csrf_token: "fresh-token" }) };
        }
        posts++;
        return { status: 400, json: async () => ({ status: "error", code: "csrf_missing" }) };
    });
    const r2 = await env2.afconPostWithCsrfRetry("/api/transport/drivers/179/location", function () {
        return { latitude: 1, longitude: 2, accuracy: 5, client_ts: Date.now() };
    });
    check("missing-no-replay", posts === 1, String(posts));
    check("missing-no-refresh-fetch", calls.filter((c) => c.url === "/api/transport/csrf-token").length === 0);
    check("missing-returns-400-to-caller", r2.status === 400);

    // --- Part 4: WIRING — real publishLocation routes through the helper ----
    calls = []; posts = 0;
    const g = makeGeoEnv(async (url, opts) => {
        calls.push({ url, headers: (opts && opts.headers) || {} });
        if (url === "/api/transport/csrf-token") {
            return { status: 200, json: async () => ({ success: true, csrf_token: "fresh-token" }) };
        }
        posts++;
        if (posts === 1) {
            return { status: 400, json: async () => ({ status: "error", code: "csrf_expired" }) };
        }
        return { status: 200, json: async () => ({ success: true }) };
    });
    await flush();
    g.geo.oneshotQueue.push({
        ok: true,
        pos: { coords: { latitude: 6.41, longitude: 2.31, accuracy: 30 }, timestamp: Date.now() },
    });
    for (let i = 0; i < 3 && posts < 1; i++) { await g.intervals[0](); await flush(); }
    check("wiring-published", posts >= 1, "posts=" + posts);
    check("wiring-one-refresh", calls.filter((c) => c.url === "/api/transport/csrf-token").length === 1);
    check("wiring-replayed-once", posts === 2, String(posts));
    const locPosts = calls.filter((c) => c.url === "/api/transport/drivers/179/location");
    check("wiring-replay-carries-fresh-token",
        locPosts.length === 2 && locPosts[1].headers["X-CSRFToken"] === "fresh-token",
        JSON.stringify(locPosts.map((c) => c.headers["X-CSRFToken"])));

    console.log(failures === 0 ? "\nALL CSRF RETRY TESTS PASSED" : `\n${failures} FAILURES`);
    process.exit(failures === 0 ? 0 : 1);
}

main().catch((e) => { console.error("HARNESS ERROR", e); process.exit(2); });
