"use strict";
// GEO realtime HTTP fallback tests. Run with plain Node, no dependencies.

const assert = require("assert");
const path = require("path");
const CLIENT = path.join(__dirname, "..", "static", "js", "geo", "geo-realtime.js");

function loadClient() {
    delete require.cache[require.resolve(CLIENT)];
    global.window = {};
    global.EventSource = undefined; // exercise the unsupported-SSE fallback
    require(CLIENT);
    return global.window.GeoRealtime;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

(async () => {
    let fetched = 0;
    let snapshot = null;
    let handle;
    global.fetch = async (url, options) => {
        fetched++;
        assert.strictEqual(url, "/geo/api/booking/TR-1/location");
        assert.strictEqual(options.credentials, "same-origin");
        return {
            ok: true,
            status: 200,
            redirected: false,
            headers: { get: (name) => name.toLowerCase() === "content-type" ? "application/json; charset=utf-8" : null },
            json: async () => ({
                success: true,
                data: {
                    version: 1,
                    event: "geo.location.updated",
                    entity_type: "driver",
                    public_ref: "DRV-1",
                    latitude: 0.3136,
                    longitude: 32.5811,
                    accuracy: null,
                    observed_at: "2026-10-31T10:00:00+00:00",
                    age_s: 0,
                    fresh: true,
                    source: "database",
                },
            }),
        };
    };
    const GeoRealtime = loadClient();
    handle = GeoRealtime.connect("/geo/stream/booking/TR-1", {
        pollUrl: "/geo/api/booking/TR-1/location",
        pollIntervalMs: 5000,
        onSnapshot: (event) => {
            snapshot = event;
            handle.close();
        },
    });
    await sleep(30);
    assert.strictEqual(fetched, 1, "fallback should issue one bounded snapshot request");
    assert(snapshot, "snapshot should reach the normal location handler");
    assert.strictEqual(snapshot.publicRef, "DRV-1");
    assert.strictEqual(snapshot.latitude, 0.3136);
    assert.strictEqual(snapshot.accuracy, null, "unknown GPS accuracy must stay unknown");

    let deniedCalls = 0;
    const states = [];
    global.fetch = async () => {
        deniedCalls++;
        return { ok: false, status: 403, redirected: false,
            headers: { get: () => "application/json" },
            json: async () => ({}) };
    };
    const GeoRealtime2 = loadClient();
    const deniedHandle = GeoRealtime2.connect("/geo/stream/booking/TR-2", {
        pollUrl: "/geo/api/booking/TR-2/location",
        pollIntervalMs: 5000,
        onState: (state) => states.push(state),
    });
    await sleep(30);
    assert.strictEqual(deniedCalls, 1, "authorization failure must not be retried");
    assert(states.includes("access-denied"), "403 must report access denial");
    assert(!states.includes("closed"), "403 must not claim the trip ended");
    deniedHandle.close();

    // A followed Flask-Login redirect can end as HTTP 200 with an HTML page.
    let redirectCalls = 0;
    const redirectStates = [];
    global.fetch = async () => {
        redirectCalls++;
        return {
            ok: true,
            status: 200,
            redirected: true,
            headers: { get: () => "text/html; charset=utf-8" },
            json: async () => { throw new Error("HTML must not be parsed as JSON"); },
        };
    };
    const GeoRealtime3 = loadClient();
    const redirectHandle = GeoRealtime3.connect("/geo/stream/booking/TR-3", {
        pollUrl: "/geo/api/booking/TR-3/location",
        pollIntervalMs: 5000,
        onState: (state) => redirectStates.push(state),
    });
    await sleep(30);
    assert.strictEqual(redirectCalls, 1, "login redirect must not be retried");
    assert(redirectStates.includes("auth-required"), "login redirect must request sign-in");
    assert(!redirectStates.includes("closed"), "login redirect must not claim the trip ended");
    redirectHandle.close();

    // Even without the redirected flag, a non-JSON 200 is not a snapshot.
    let htmlCalls = 0;
    const htmlStates = [];
    global.fetch = async () => {
        htmlCalls++;
        return {
            ok: true,
            status: 200,
            redirected: false,
            headers: { get: () => "text/html; charset=utf-8" },
            json: async () => { throw new Error("HTML must not be parsed as JSON"); },
        };
    };
    const GeoRealtime4 = loadClient();
    const htmlHandle = GeoRealtime4.connect("/geo/stream/booking/TR-4", {
        pollUrl: "/geo/api/booking/TR-4/location",
        pollIntervalMs: 5000,
        onState: (state) => htmlStates.push(state),
    });
    await sleep(30);
    assert.strictEqual(htmlCalls, 1, "non-JSON responses must not be retried");
    assert(htmlStates.includes("unavailable"), "non-JSON response must report tracking unavailable");
    assert(!htmlStates.includes("closed"), "HTML response must not claim the trip ended");
    htmlHandle.close();

    // A direct 401 is an expired session even when the response is JSON.
    let expiredCalls = 0;
    const expiredStates = [];
    global.fetch = async () => {
        expiredCalls++;
        return {
            ok: false,
            status: 401,
            redirected: false,
            headers: { get: () => "application/json" },
            json: async () => ({ success: false }),
        };
    };
    const GeoRealtime5 = loadClient();
    const expiredHandle = GeoRealtime5.connect("/geo/stream/booking/TR-5", {
        pollUrl: "/geo/api/booking/TR-5/location",
        pollIntervalMs: 5000,
        onState: (state) => expiredStates.push(state),
    });
    await sleep(30);
    assert.strictEqual(expiredCalls, 1, "401 must not be retried");
    assert(expiredStates.includes("auth-required"), "401 must request sign-in");
    assert(!expiredStates.includes("closed"), "401 must not claim the trip ended");
    expiredHandle.close();

    // A missing booking/endpoint is not proof of trip completion either.
    let missingCalls = 0;
    const missingStates = [];
    global.fetch = async () => {
        missingCalls++;
        return {
            ok: false,
            status: 404,
            redirected: false,
            headers: { get: () => "application/json" },
            json: async () => ({ success: false }),
        };
    };
    const GeoRealtime6 = loadClient();
    const missingHandle = GeoRealtime6.connect("/geo/stream/booking/TR-6", {
        pollUrl: "/geo/api/booking/TR-6/location",
        pollIntervalMs: 5000,
        onState: (state) => missingStates.push(state),
    });
    await sleep(30);
    assert.strictEqual(missingCalls, 1, "404 must not be retried");
    assert(missingStates.includes("unavailable"), "404 must report tracking unavailable");
    assert(!missingStates.includes("closed"), "404 must not claim the trip ended");
    missingHandle.close();

    console.log("GEO HTTP FALLBACK: ALL PASS");
})().catch((error) => {
    console.error(error && error.stack || error);
    process.exitCode = 1;
});
