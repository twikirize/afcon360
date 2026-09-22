(function() {
    'use strict';

    // ============================================================
    // CONFIG
    // ============================================================
    var CONFIG = {
        endpoint:    '/admin/owner/production-console/frontend-event',
        historyPath: '/admin/owner/production-console/history',

        // FIX: budgets are now well below the server's 2000/day cap.
        //      These are shared across tabs (localStorage), not per-page.
        maxPerMinute: 20,
        maxPerDay:    1000,

        maxMessageLen: 500,

        // FIX: concurrent-request cap so a burst can't fire hundreds at once.
        maxInflight: 3,

        // FIX: circuit-breaker cooldown when the server says 429/401/403.
        cooldownMs: 5 * 60 * 1000,

        // FIX: don't log every successful fetch — that was the main source
        //      of the event flood. Only log errors and slow requests.
        logSuccessfulFetches: false,
        slowFetchMs: 2000,
    };

    var STORAGE_KEY = 'fc_tracker_budget_v2';

    var SENSITIVE_PARAMS = [
        'token', 'api_key', 'apikey', 'secret', 'password', 'passwd', 'auth',
        'jwt', 'access_token', 'refresh_token', 'csrf', 'csrf_token', 'signature',
        'key', 'otp', 'code', 'pin', 'card', 'cvv', 'authorization'
    ];

    // FIX: capture native fetch ONCE, at the top, before we wrap window.fetch.
    //      All telemetry uses this — so our own POSTs never re-enter the wrapper.
    var nativeFetch = window.fetch;

    // ============================================================
    // STATE
    // ============================================================
    var disabled  = false;
    var inFlight  = 0;

    // ============================================================
    // BUDGET  (persisted across reloads and tabs)
    // ============================================================
    function todayKey() {
        var d = new Date();
        return d.getFullYear() + '-' + (d.getMonth() + 1) + '-' + d.getDate();
    }

    function readBudget() {
        var empty = { day: todayKey(), dayCount: 0, minuteStart: Date.now(), minuteCount: 0 };
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return empty;
            var b = JSON.parse(raw);
            if (!b || b.day !== todayKey()) return empty;
            return b;
        } catch (e) {
            return empty;
        }
    }

    function writeBudget(b) {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(b)); } catch (e) {}
    }

    // FIX: single atomic check-and-charge. Original code had separate
    //      throttle() + counter increment, which reset on every page load.
    function tryChargeBudget() {
        var b = readBudget();
        var now = Date.now();

        if (b.dayCount >= CONFIG.maxPerDay) return false;

        if (now - b.minuteStart > 60000) {
            b.minuteStart = now;
            b.minuteCount = 0;
        }
        if (b.minuteCount >= CONFIG.maxPerMinute) return false;

        b.dayCount++;
        b.minuteCount++;
        writeBudget(b);
        return true;
    }

    // ============================================================
    // HELPERS
    // ============================================================
    function isAuthenticated() {
        var meta = document.querySelector('meta[name="user-authenticated"]');
        return !!meta && meta.content === 'true';
    }

    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    }

    function getCorrelationId() {
        var meta = document.querySelector('meta[name="correlation-id"]');
        if (meta) return meta.content;
        try { return localStorage.getItem('correlation_id') || null; }
        catch (e) { return null; }
    }

    function sanitizeUrl(url) {
        if (!url) return url;
        try {
            var u = new URL(url, window.location.href);
            var changed = false;
            SENSITIVE_PARAMS.forEach(function(k) {
                if (u.searchParams.has(k)) {
                    u.searchParams.set(k, '***');
                    changed = true;
                }
            });
            if (u.search && u.search.length > 80) {
                u.search = '';
                changed = true;
            }
            return changed ? (u.pathname + u.search) : url;
        } catch (e) {
            return url;
        }
    }

    function isOwnTraffic(url) {
        if (!url) return false;
        return url.indexOf(CONFIG.endpoint)    !== -1 ||
               url.indexOf(CONFIG.historyPath) !== -1;
    }

    // ============================================================
    // CIRCUIT BREAKER  — new
    // ============================================================
    function trip(reason) {
        if (disabled) return;
        disabled = true;
        try {
            console.warn('[frontend-tracker] paused: ' + reason +
                         ' (cooldown ' + Math.round(CONFIG.cooldownMs / 1000) + 's)');
        } catch (e) {}
        setTimeout(function() {
            disabled = false;
            try { console.info('[frontend-tracker] resumed'); } catch (e) {}
        }, CONFIG.cooldownMs);
    }

    // ============================================================
    // SEND
    // ============================================================
    function sendEvent(data) {
        // FIX: respect circuit breaker first.
        if (disabled) return;
        if (!nativeFetch) return;
        if (!isAuthenticated()) return;
        if (inFlight >= CONFIG.maxInflight) return;
        // FIX: budget check happens here, once, atomically.
        if (!tryChargeBudget()) return;

        var payload;
        try {
            payload = JSON.stringify({
                severity: data.severity || 'INFO',
                category: data.category || 'FRONTEND',
                message: String(data.message || '').slice(0, CONFIG.maxMessageLen),
                frontend: data.frontend || {},
                correlation_id: data.correlation_id || getCorrelationId(),
            });
        } catch (e) {
            return;
        }

        inFlight++;

        // FIX: use nativeFetch (not window.fetch) so telemetry never loops
        //      back through the fetch interceptor.
        nativeFetch(CONFIG.endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            body: payload,
            credentials: 'same-origin',
            // FIX: dropped keepalive:true — it's for unload beacons, not every event.
        }).then(function(res) {
            inFlight--;
            // FIX: actually READ the status. Original code only had .catch(),
            //      which never fires for a 429 (it's a successful fetch).
            if (res.status === 429) {
                trip('HTTP 429 from server');
            } else if (res.status === 401 || res.status === 403) {
                trip('HTTP ' + res.status + ' from server');
            }
        }).catch(function() {
            inFlight--;
        });
    }

    // ============================================================
    // SELECTOR
    // ============================================================
    function getSelector(el) {
        if (!el) return 'unknown';
        if (el.id) return '#' + el.id;
        var cn = el.className;
        if (cn && typeof cn === 'string') {
            return el.tagName.toLowerCase() + '.' + cn.split(' ').slice(0, 2).join('.');
        }
        return el.tagName.toLowerCase();
    }

    // ============================================================
    // CLICK CAPTURE
    // ============================================================
    document.addEventListener('click', function(e) {
        var target = e.target && e.target.closest
            ? e.target.closest('a, button, [role="button"], input[type="submit"], input[type="image"]')
            : null;
        if (!target) return;

        var tag = target.tagName.toLowerCase();
        var message = '';
        var action = 'click';

        if (tag === 'a') {
            var href = sanitizeUrl(target.getAttribute('href') || '');
            message = 'Navigated: ' + (href || '(no href)');
            action = 'navigation';
        } else if (tag === 'button' || target.hasAttribute('role')) {
            var text = (target.textContent || target.innerText || '').trim().slice(0, 50);
            message = 'Clicked: ' + (text || target.id || 'button');
        } else if (target.type === 'submit') {
            message = 'Submitted: ' + (target.form
                ? (target.form.id || target.form.className || 'form')
                : 'form');
            action = 'form_submit';
        }

        if (!message) return;

        sendEvent({
            severity: 'INFO',
            category: 'FRONTEND',
            message: message,
            frontend: {
                action: action,
                selector: getSelector(target),
                url: window.location.href,
            }
        });
    }, true);

    // ============================================================
    // FORM SUBMIT CAPTURE
    // ============================================================
    document.addEventListener('submit', function(e) {
        var form = e.target;
        sendEvent({
            severity: 'INFO',
            category: 'FRONTEND',
            message: 'Form submitted: ' + (form.id || form.className || form.tagName.toLowerCase()),
            frontend: {
                action: 'form_submit',
                selector: form.id ? '#' + form.id : form.tagName.toLowerCase(),
                url: window.location.href,
                method: (form.method || 'GET').toUpperCase(),
            }
        });
    }, true);

    // ============================================================
    // FETCH INTERCEPTOR
    // ============================================================
    if (nativeFetch) {
        window.fetch = function() {
            var args = Array.prototype.slice.call(arguments);
            var start = performance.now();
            var rawUrl = typeof args[0] === 'string'
                ? args[0]
                : (args[0] && args[0].url ? args[0].url : '');

            // Never log our own traffic (prevents feedback loop).
            if (isOwnTraffic(rawUrl)) {
                return nativeFetch.apply(this, args);
            }

            var safeUrl = sanitizeUrl(rawUrl);

            return nativeFetch.apply(this, args).then(function(response) {
                var duration = Math.round(performance.now() - start);
                var status = response.status;

                // FIX: only log when there's actually something to log.
                //      Successful + fast fetches are silent now.
                var shouldLog =
                    status >= 400 ||
                    duration > CONFIG.slowFetchMs ||
                    CONFIG.logSuccessfulFetches;

                if (shouldLog) {
                    var severity =
                        status >= 500                     ? 'ERROR'   :
                        status >= 400                     ? 'WARNING' :
                        duration > CONFIG.slowFetchMs     ? 'WARNING' :
                                                            'INFO';

                    sendEvent({
                        severity: severity,
                        category: 'NETWORK',
                        message: 'Fetch ' + status + ': ' + (safeUrl || 'unknown') +
                                 ' (' + duration + 'ms)',
                        frontend: {
                            action: 'fetch',
                            url: safeUrl,
                            status: status,
                            duration_ms: duration,
                        }
                    });
                }
                return response;
            }).catch(function(err) {
                var duration = Math.round(performance.now() - start);
                sendEvent({
                    severity: 'ERROR',
                    category: 'NETWORK',
                    message: 'Fetch failed: ' + (safeUrl || 'unknown') +
                             ' (' + duration + 'ms)',
                    frontend: {
                        action: 'fetch_error',
                        url: safeUrl,
                        error: err && err.message ? err.message : String(err),
                        duration_ms: duration,
                    }
                });
                throw err;
            });
        };
    }

    // ============================================================
    // WINDOW ERROR CAPTURE
    // ============================================================
    window.addEventListener('error', function(e) {
        var t = e.target;

        // Resource load failure
        if (t && t !== window && t.nodeType === 1 &&
            ['IMG', 'SCRIPT', 'LINK', 'IFRAME'].indexOf(t.tagName) !== -1) {
            var src = sanitizeUrl(t.src || t.href || '');
            sendEvent({
                severity: 'ERROR',
                category: 'NETWORK',
                message: 'Resource failed: ' + t.tagName + ' ' + (src || '(unknown)'),
                frontend: {
                    action: 'resource_error',
                    url: src,
                    target: t.tagName,
                }
            });
            return;
        }

        // JS runtime error
        sendEvent({
            severity: 'ERROR',
            category: 'ERROR',
            message: 'Unhandled error: ' + (e.message || 'Unknown'),
            frontend: {
                action: 'unhandled_error',
                filename: e.filename,
                lineno: e.lineno,
                colno: e.colno,
                url: window.location.href,
            }
        });
    }, true);

    // ============================================================
    // UNHANDLED PROMISE REJECTION
    // ============================================================
    window.addEventListener('unhandledrejection', function(e) {
        var reason = e.reason && e.reason.message
            ? e.reason.message
            : String(e.reason || 'Unknown');
        sendEvent({
            severity: 'ERROR',
            category: 'ERROR',
            message: 'Unhandled rejection: ' + reason,
            frontend: {
                action: 'unhandled_rejection',
                reason: reason,
                url: window.location.href,
            }
        });
    });

    // ============================================================
    // CONSOLE MIRRORING
    // ============================================================
    ['error', 'warn'].forEach(function(level) {
        var original = console[level];
        console[level] = function() {
            try {
                var args = Array.prototype.slice.call(arguments);
                var parts = args.map(function(a) {
                    if (a instanceof Error) return a.message;
                    if (typeof a === 'object' && a !== null) {
                        try { return JSON.stringify(a); }
                        catch (err) { return String(a); }
                    }
                    return String(a);
                });
                var text = parts.join(' ').slice(0, CONFIG.maxMessageLen);
                sendEvent({
                    severity: level === 'error' ? 'ERROR' : 'WARNING',
                    category: level === 'error' ? 'ERROR' : 'FRONTEND',
                    message: 'console.' + level + ': ' + text,
                    frontend: {
                        action: 'console_' + level,
                        text: text,
                    }
                });
            } catch (err) { /* never break app logging */ }
            return original.apply(console, arguments);
        };
    });

    // ============================================================
    // PAGE-LOAD PERFORMANCE
    // ============================================================
    function capturePerformance() {
        if (!window.performance) return;
        var nav = performance.getEntriesByType('navigation')[0];
        if (!nav) return;

        var metrics = {
            domContentLoaded: Math.round(nav.domContentLoadedEventEnd - nav.startTime),
            loadComplete:     Math.round(nav.loadEventEnd - nav.startTime),
            responseTime:     Math.round(nav.responseEnd - nav.requestStart),
            domProcessing:    Math.round(nav.domInteractive - nav.startTime),
        };
        if (metrics.loadComplete <= 0) return;

        var status = (typeof nav.responseStatus !== 'undefined') ? nav.responseStatus : null;

        if (status && status >= 400) {
            sendEvent({
                severity: status >= 500 ? 'ERROR' : 'WARNING',
                category: 'ERROR',
                message: 'Page load failed: HTTP ' + status + ' ' + window.location.href,
                frontend: {
                    action: 'page_load_error',
                    url: window.location.href,
                    status: status,
                    loadComplete: metrics.loadComplete,
                }
            });
            return;
        }

        var severity = metrics.loadComplete > 3000 ? 'WARNING' : 'INFO';
        sendEvent({
            severity: severity,
            category: 'PERFORMANCE',
            message: 'Page load: ' + metrics.loadComplete + 'ms (DOM: ' +
                     metrics.domContentLoaded + 'ms, Response: ' +
                     metrics.responseTime + 'ms)',
            frontend: {
                action: 'page_load',
                url: window.location.href,
                domContentLoaded: metrics.domContentLoaded,
                loadComplete:     metrics.loadComplete,
                responseTime:     metrics.responseTime,
                domProcessing:    metrics.domProcessing,
            }
        });
    }

    if (document.readyState === 'complete') {
        capturePerformance();
    } else {
        window.addEventListener('load', capturePerformance);
    }

    // ============================================================
    // VISIBILITY CHANGES
    // ============================================================
    document.addEventListener('visibilitychange', function() {
        sendEvent({
            severity: 'INFO',
            category: 'FRONTEND',
            message: 'Visibility: ' + document.visibilityState,
            frontend: {
                action: 'visibility_change',
                state: document.visibilityState,
                url: window.location.href,
            }
        });
    });

    // ============================================================
    // DEBUG HANDLE  — open console and run window.__frontendTracker.status()
    // ============================================================
    window.__frontendTracker = {
        config: CONFIG,
        status: function() {
            var b = readBudget();
            return {
                disabled:     disabled,
                inFlight:     inFlight,
                dayCount:     b.dayCount,
                dayBudget:    CONFIG.maxPerDay,
                minuteCount:  b.minuteCount,
                minuteBudget: CONFIG.maxPerMinute,
            };
        },
        trip: function(reason) { trip(reason || 'manual'); },
        reset: function() {
            disabled = false;
            inFlight = 0;
            try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
        },
    };
})();