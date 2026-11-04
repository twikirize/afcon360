"use strict";
// Contract tests for the frozen AFCON360 driver-dashboard.js.
// The production file deliberately exports only pure policy helpers under
// Node. Browser-only closures are source-guarded here and exercised in the
// authenticated Flask/CSRF integration tests; do not rewrite the frozen JS
// just to expose private browser functions to this harness.

const fs = require("fs");
const path = require("path");
const DASH = path.join(__dirname, "..", "static", "js", "modules", "transport", "driver-dashboard.js");

let failures = 0;
function check(name, condition, detail) {
    if (condition) {
        console.log("ok   " + name);
    } else {
        failures++;
        console.log("FAIL " + name + (detail ? " :: " + detail : ""));
    }
}

const policy = require(DASH);
const shouldRetry = policy.afconShouldRetryAfter400;
const classify = policy.afconClassifyResponse;
const retryAfter = policy.afconParseRetryAfterMs;

check("predicate-exported", typeof shouldRetry === "function");
check("classifier-exported", typeof classify === "function");
check("retry-after-exported", typeof retryAfter === "function");

// These expectations intentionally match the frozen v2.5.2 source:
// both explicit CSRF-expired and CSRF-missing responses trigger one refresh.
check("expired-refreshable", shouldRetry(400, { code: "csrf_expired" }) === true);
check("missing-refreshable", shouldRetry(400, { code: "csrf_missing" }) === true);
check("invalid-does-not-retry", shouldRetry(400, { code: "csrf_invalid" }) === false);
check("plain-400-no-retry", shouldRetry(400, { error: "bad payload" }) === false);
check("non-400-no-retry", shouldRetry(200, { code: "csrf_expired" }) === false);
check("null-body-no-retry", shouldRetry(400, null) === false);
check("string-body-parsed", shouldRetry(400, '{"code":"csrf_expired"}') === true);
check("garbage-string-no-retry", shouldRetry(400, "<html>nope") === false);

check("2xx-classifies-success", classify(204, null) === "success");
check("401-classifies-auth-required", classify(401, null) === "auth-required");
check("403-classifies-authorization-failure", classify(403, null) === "authorization-failure");
check("404-classifies-configuration-error", classify(404, null) === "configuration-error");
check("409-classifies-conflict", classify(409, null) === "conflict");
check("422-classifies-validation-error", classify(422, null) === "validation-error");
check("429-classifies-rate-limit", classify(429, null) === "rate-limited");
check("5xx-classifies-server-error", classify(503, null) === "server-error");

check("retry-after-seconds", retryAfter("3") === 3000);
check("retry-after-zero", retryAfter("0") === 0);
check("retry-after-empty", retryAfter("") === null);
check("retry-after-invalid", retryAfter("not-a-date") === null);

// The private retry helper is intentionally not exported in Node mode.
// Guard its actual browser wiring without changing the frozen production JS.
const source = fs.readFileSync(DASH, "utf8");
const wiringChecks = [
    ["private-retry-helper-exists", "async function afconPostWithCsrfRetry(url, buildBody, signal, gen) {"],
    ["retry-checks-explicit-csrf-code", "if (!afconShouldRetryAfter400(result.status, result.data)) return result;"],
    ["retry-refreshes-session-token", "var refreshed = await refreshCsrfToken();"],
    ["retry-stops-when-refresh-fails", "if (!refreshed) return result;"],
    ["retry-replays-once", "return await postJSON(url, buildBody(), signal);"],
    ["publisher-uses-retry-helper", "var result = await afconPostWithCsrfRetry("],
    ["refresh-is-no-store", 'cache: "no-store"'],
    ["refresh-is-same-origin", 'credentials: "same-origin"']
];
for (const [name, fragment] of wiringChecks) {
    check(name, source.includes(fragment));
}

if (failures) {
    console.log("\\n" + failures + " FAILURE(S)");
    process.exit(1);
}
console.log("\\nALL DRIVER CSRF CONTRACT TESTS PASSED");
