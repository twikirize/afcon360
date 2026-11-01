"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const template = fs.readFileSync(
  path.join(__dirname, "..", "templates", "transport", "rides", "request_show.html"),
  "utf8"
);
const match = template.match(
  /<script nonce="\{\{ csp_nonce \}\}">([\s\S]*?)<\/script>/
);
assert(match, "request tracker inline script must be present");
assert(match[1].includes("var inFlight = false;"));
assert(match[1].includes("REQUEST_TIMEOUT_MS = 10000"));
assert(match[1].includes("schedulePoll(nextDelay)"));
assert(!match[1].includes("setInterval(poll"));
new Function(match[1]); // syntax-check only; do not execute the browser client
console.log("REQUEST TRACKER INLINE JS: SYNTAX PASS");
