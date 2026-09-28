"use strict";
// Deterministic tests for the rider bounded matching search (FS-6b).
// Runs under plain node (no deps): `node tests/test_rider_matching_search.cjs`.
//
// Covers: budget exhaustion -> terminal no-supply state + polling stops;
// assignment at the boundary wins; cancellation intact; explicit Try Again
// reuses the same booking (no second booking, no backend state change);
// timer cleanup (status + availability + failure retry cannot resurrect).
//
// The module executes on require, so browser globals are stubbed BEFORE
// each require (fresh module per scenario via cache busting).

const path = require("path");
const RM = path.join(__dirname, "..", "static", "js", "modules", "transport", "rider_matching.js");

let failures = 0;
function check(name, cond, extra) {
    if (cond) { console.log("ok   " + name); }
    else { failures++; console.log("FAIL " + name + (extra ? " :: " + extra : "")); }
}
const flush = async (n) => { for (let i = 0; i < (n || 12); i++) await new Promise((r) => setImmediate(r)); };

// --- stub environment --------------------------------------------------------
function makeEnv(statusScript) {
    const calls = { fetch: [], timeouts: [], intervals: [], cleared: [], events: [], reloads: 0 };
    const queue = (statusScript || []).slice();
    const els = {};
    function el(id) {
        if (!els[id]) {
            els[id] = {
                id, className: "", textContent: "", innerHTML: "",
                children: [], handlers: {},
                getAttribute: () => null,
                appendChild(c) { this.children.push(c); return c; },
                addEventListener(ev, fn) { this.handlers[ev] = fn; },
            };
        }
        return els[id];
    }
    const panel = el("riderMatching");
    const attrs = {
        "data-status-url": "/api/transport/bookings/REF123",
        "data-options-url": "/api/transport/ride-options",
        "data-csrf": "csrf-token",
        "data-service-type": "on_demand",
        "data-currency": "USD",
    };
    panel.getAttribute = (k) => attrs[k] || null;
    const buttons = [];
    const timeouts = [];
    const intervals = [];
    let timerSeq = 0;

    global.document = {
        getElementById: (id) => (id === "riderMatching" ? panel : el(id)),
        createElement: (tag) => {
            const b = {
                tag, type: "", className: "", textContent: "", handlers: {},
                addEventListener(ev, fn) { this.handlers[ev] = fn; },
                click() { if (this.handlers.click) this.handlers.click(); },
            };
            buttons.push(b);
            return b;
        },
    };
    global.window = {
        dispatchEvent: (ev) => { calls.events.push(ev); },
        location: { reload: () => { calls.reloads++; } },
    };
    global.fetch = (url, opts) => {
        const method = (opts && opts.method) || "GET";
        calls.fetch.push({ url, method });
        if (String(url).includes("ride-options")) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { options: [] } }) });
        }
        const st = queue.length ? queue.shift() : "confirmed";
        if (st === "__reject__") return Promise.reject(new Error("net down"));
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { booking: { status: st } } }) });
    };
    global.setTimeout = (fn, ms) => { const id = ++timerSeq; timeouts.push({ id, fn, ms }); return id; };
    global.clearTimeout = (id) => {
        const i = timeouts.findIndex((t) => t.id === id);
        if (i >= 0) timeouts.splice(i, 1);
    };
    global.setInterval = (fn, ms) => { const id = ++timerSeq; intervals.push({ id, fn, ms }); return id; };
    global.clearInterval = (id) => { calls.cleared.push(id); };
    return { calls, els, panel, buttons, timeouts, intervals };
}

function loadFresh() {
    delete require.cache[require.resolve(RM)];
    return require(RM);
}

async function stepTimeouts(env, n) {
    for (let i = 0; i < n; i++) {
        const t = env.timeouts.shift();
        if (!t) break;
        t.fn();
        await flush();
    }
}

function statusFetches(env) {
    return env.calls.fetch.filter((c) => String(c.url).includes("/api/transport/bookings/"));
}

// --- Test 1: bounded search -> terminal, polling stops -----------------------
(async () => {
    const env = makeEnv([]);
    loadFresh();
    await flush();
    await stepTimeouts(env, 70); // 60 matching polls exhaust the budget
    await flush();
    const avail = env.els.rmAvail.textContent;
    check("t1-terminal-copy", avail.includes("No drivers available right now"), avail);
    check("t1-retry-button", env.buttons.length === 1 && env.buttons[0].textContent === "Try Again", String(env.buttons.length));
    const fetchCount = env.calls.fetch.length;
    const timeoutsLeft = env.timeouts.length;
    await stepTimeouts(env, 10);
    await flush();
    check("t1-polling-stopped", env.calls.fetch.length === fetchCount && env.timeouts.length === timeoutsLeft,
        `fetch ${fetchCount}->${env.calls.fetch.length}`);
    check("t1-interval-cleared", env.calls.cleared.length >= 1, JSON.stringify(env.calls.cleared));
})()
.then(async () => {
    // --- Test 2: assignment at the boundary wins ---------------------------
    const env = makeEnv(["confirmed", "confirmed", "confirmed", "confirmed", "confirmed", "assigned"]);
    loadFresh();
    await flush();
    await stepTimeouts(env, 10);
    await flush();
    check("t2-handoff", env.calls.events.length === 1 && env.calls.events[0].detail.status === "assigned",
        JSON.stringify(env.calls.events.map((e) => e.detail)));
    check("t2-no-terminal", !env.els.rmAvail.textContent.includes("No drivers available"), env.els.rmAvail.textContent);
    check("t2-no-retry-button", env.buttons.length === 0, String(env.buttons.length));
})
.then(async () => {
    // --- Test 3: cancellation intact ---------------------------------------
    const env = makeEnv(["confirmed", "cancelled"]);
    loadFresh();
    await flush();
    await stepTimeouts(env, 4);
    await flush();
    check("t3-reload-on-cancel", env.calls.reloads === 1, String(env.calls.reloads));
    check("t3-no-terminal", !env.els.rmAvail.textContent.includes("No drivers available"), env.els.rmAvail.textContent);
})
.then(async () => {
    // --- Test 4+5: explicit retry reuses the same booking ------------------
    const env = makeEnv([]);
    loadFresh();
    await flush();
    await stepTimeouts(env, 70);
    await flush();
    check("t4-terminal-reached", env.buttons.length === 1, String(env.buttons.length));
    const urlsBefore = env.calls.fetch.map((c) => c.method + " " + c.url);
    const statusCountBefore = statusFetches(env).length;
    env.buttons[0].click();
    await flush();
    await stepTimeouts(env, 3);
    await flush();
    const urlsAfter = env.calls.fetch.map((c) => c.method + " " + c.url);
    const newCalls = urlsAfter.slice(urlsBefore.length);
    check("t4-retry-resumes-polling", newCalls.length > 0 && statusFetches(env).length > statusCountBefore,
        JSON.stringify(newCalls));
    const bookingWrites = newCalls.filter((u) => !u.includes("/api/transport/bookings/") && !u.includes("ride-options"));
    check("t5-no-second-booking", bookingWrites.length === 0, JSON.stringify(newCalls));
    const statusUrls = new Set(statusFetches(env).map((c) => c.url));
    check("t5-same-booking", statusUrls.size === 1 && [...statusUrls][0].includes("REF123"), JSON.stringify([...statusUrls]));
    check("t4-terminal-cleared", !env.els.rmAvail.textContent.includes("No drivers available"), env.els.rmAvail.textContent);
})
.then(async () => {
    // --- Test 6: timer cleanup ---------------------------------------------
    const env = makeEnv([]);
    const api = loadFresh();
    await flush();
    check("t6-budget-named", api.SEARCH_BUDGET_POLLS === 60, String(api.SEARCH_BUDGET_POLLS));
    check("t6-policy-pure", api.isMatchingStatus("confirmed") && !api.isMatchingStatus("assigned") && api.budgetExhausted(60) && !api.budgetExhausted(59), "");
    await stepTimeouts(env, 70);
    await flush();
    // Stale interval callback must be harmless (finished guard).
    for (const iv of env.intervals) { iv.fn(); await flush(); }
    const afterTerminal = env.calls.fetch.length;
    await stepTimeouts(env, 5);
    await flush();
    check("t6-no-resurrection", env.calls.fetch.length === afterTerminal,
        `fetch ${afterTerminal}->${env.calls.fetch.length}`);
    // Transient failure never reads as no-drivers and never bypasses budget.
    const env2 = makeEnv(["__reject__", "__reject__", "confirmed"]);
    loadFresh();
    await flush();
    await stepTimeouts(env2, 6);
    await flush();
    check("t6-failure-not-terminal", !env2.els.rmAvail.textContent.includes("No drivers available"), env2.els.rmAvail.textContent);
})
.then(() => {
    console.log(failures === 0 ? "ALL PASS" : failures + " FAILURES");
    if (failures) process.exitCode = 1;
})
.catch((e) => { console.log("HARNESS ERROR " + (e && e.stack || e)); process.exitCode = 1; });
