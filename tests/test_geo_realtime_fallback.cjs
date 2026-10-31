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
        return { ok: false, status: 403, json: async () => ({}) };
    };
    const GeoRealtime2 = loadClient();
    const deniedHandle = GeoRealtime2.connect("/geo/stream/booking/TR-2", {
        pollUrl: "/geo/api/booking/TR-2/location",
        pollIntervalMs: 5000,
        onState: (state) => states.push(state),
    });
    await sleep(30);
    assert.strictEqual(deniedCalls, 1, "authorization failure must not be retried");
    assert(states.includes("closed"), "authorization failure must close tracking");
    deniedHandle.close();
    console.log("GEO HTTP FALLBACK: ALL PASS");
})().catch((error) => {
    console.error(error && error.stack || error);
    process.exitCode = 1;
});
