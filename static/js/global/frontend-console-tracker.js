(function() {
    'use strict';

    const CONSOLE_ENDPOINT = '/admin/owner/production-console/frontend-event';
    const CONSOLE_PATH = '/admin/owner/production-console';
    const MAX_EVENTS_PER_MINUTE = 30;
    const MAX_MESSAGE_LEN = 500;

    // Query-param keys that may carry secrets/PII and must never be logged verbatim
    const SENSITIVE_PARAMS = [
        'token', 'api_key', 'apikey', 'secret', 'password', 'passwd', 'auth',
        'jwt', 'access_token', 'refresh_token', 'csrf', 'csrf_token', 'signature',
        'key', 'otp', 'code', 'pin', 'card', 'cvv', 'authorization'
    ];

    let eventCount = 0;
    let lastReset = Date.now();

    function isConsolePage() {
        return window.location.pathname === CONSOLE_PATH;
    }

    function isAuthenticated() {
        const meta = document.querySelector('meta[name="user-authenticated"]');
        return meta && meta.content === 'true';
    }

    function throttle() {
        const now = Date.now();
        if (now - lastReset > 60000) {
            eventCount = 0;
            lastReset = now;
        }
        if (eventCount >= MAX_EVENTS_PER_MINUTE) {
            return false;
        }
        eventCount++;
        return true;
    }

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    }

    function getCorrelationId() {
        const meta = document.querySelector('meta[name="correlation-id"]');
        if (meta) return meta.content;
        return localStorage.getItem('correlation_id') || null;
    }

    // Remove secrets/PII from URLs before they are logged
    function sanitizeUrl(url) {
        if (!url) return url;
        try {
            const u = new URL(url, window.location.href);
            let changed = false;
            SENSITIVE_PARAMS.forEach(function(k) {
                if (u.searchParams.has(k)) {
                    u.searchParams.set(k, '***');
                    changed = true;
                }
            });
            // Drop overly long query strings entirely (avoid noise + leak)
            if (u.search && u.search.length > 80) {
                u.search = '';
                changed = true;
            }
            return changed ? (u.pathname + u.search) : url;
        } catch (e) {
            return url;
        }
    }

    function sendEvent(data) {
        if (!isAuthenticated()) return;
        if (!throttle()) return;

        const payload = JSON.stringify({
            severity: data.severity || 'INFO',
            category: data.category || 'FRONTEND',
            message: (data.message || '').slice(0, MAX_MESSAGE_LEN),
            frontend: data.frontend || {},
            correlation_id: data.correlation_id || getCorrelationId(),
        });

        fetch(CONSOLE_ENDPOINT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            body: payload,
            keepalive: true,
        }).catch(function() {});
    }

    function getSelector(el) {
        if (el.id) return '#' + el.id;
        if (el.className && typeof el.className === 'string') {
            return el.tagName.toLowerCase() + '.' + el.className.split(' ').slice(0, 2).join('.');
        }
        return el.tagName.toLowerCase();
    }

    // ---- Capture meaningful clicks / navigation ----
    document.addEventListener('click', function(e) {
        const target = e.target.closest('a, button, [role="button"], input[type="submit"], input[type="image"]');
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
            message = 'Submitted: ' + (target.form ? (target.form.id || target.form.className || 'form') : 'form');
            action = 'form_submit';
        }

        if (message) {
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
        }
    }, true);

    // ---- Capture form submissions ----
    document.addEventListener('submit', function(e) {
        var form = e.target;
        var message = 'Form submitted: ' + (form.id || form.className || form.tagName.toLowerCase());
        sendEvent({
            severity: 'INFO',
            category: 'FRONTEND',
            message: message,
            frontend: {
                action: 'form_submit',
                selector: form.id ? '#' + form.id : form.tagName.toLowerCase(),
                url: window.location.href,
                method: (form.method || 'GET').toUpperCase(),
            }
        });
    }, true);

    // ---- Intercept fetch (network events) ----
    var originalFetch = window.fetch;
    window.fetch = function() {
        var args = Array.prototype.slice.call(arguments);
        var start = performance.now();
        var rawUrl = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url ? args[0].url : '');
        var url = sanitizeUrl(rawUrl);

        // Never log the console's own reporting/polling traffic (prevents feedback loop)
        if (rawUrl && (rawUrl.indexOf(CONSOLE_ENDPOINT) !== -1 || rawUrl.indexOf('/admin/owner/production-console/history') !== -1)) {
            return originalFetch.apply(this, args);
        }

        return originalFetch.apply(this, args).then(function(response) {
            var duration = Math.round(performance.now() - start);
            var status = response.status;
            var severity = status >= 500 ? 'ERROR' : (status >= 400 ? 'WARNING' : (duration > 3000 ? 'WARNING' : 'INFO'));
            sendEvent({
                severity: severity,
                category: 'NETWORK',
                message: 'Fetch ' + status + ': ' + (url || 'unknown') + ' (' + duration + 'ms)',
                frontend: {
                    action: 'fetch',
                    url: url,
                    status: status,
                    duration_ms: duration,
                }
            });
            return response;
        }).catch(function(err) {
            var duration = Math.round(performance.now() - start);
            sendEvent({
                severity: 'ERROR',
                category: 'NETWORK',
                message: 'Fetch failed: ' + (url || 'unknown') + ' (' + duration + 'ms)',
                frontend: {
                    action: 'fetch_error',
                    url: url,
                    error: err.message,
                    duration_ms: duration,
                }
            });
            throw err;
        });
    };

    // ---- Capture runtime + resource-load errors ----
    window.addEventListener('error', function(e) {
        // Resource load failure (img / script / link / iframe)
        var t = e.target;
        if (t && t !== window && t.nodeType === 1 && ['IMG', 'SCRIPT', 'LINK', 'IFRAME'].indexOf(t.tagName) !== -1) {
            var src = sanitizeUrl(t.src || t.href || '');
            sendEvent({
                severity: 'ERROR',
                category: 'NETWORK',
                message: 'Resource failed to load: ' + t.tagName + ' ' + (src || '(unknown)'),
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

    // ---- Capture unhandled promise rejections ----
    window.addEventListener('unhandledrejection', function(e) {
        var reason = e.reason && e.reason.message ? e.reason.message : String(e.reason || 'Unknown');
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

    // ---- Mirror console.error / console.warn into the console ----
    // (captures developer errors like the shell terminal; string-only, truncated)
    ['error', 'warn'].forEach(function(level) {
        var original = console[level];
        console[level] = function() {
            try {
                var args = Array.prototype.slice.call(arguments);
                var parts = args.map(function(a) {
                    if (a instanceof Error) return a.message;
                    if (typeof a === 'object' && a !== null) {
                        try { return JSON.stringify(a); } catch (err) { return String(a); }
                    }
                    return String(a);
                });
                var text = parts.join(' ').slice(0, MAX_MESSAGE_LEN);
                sendEvent({
                    severity: level === 'error' ? 'ERROR' : 'WARNING',
                    category: level === 'error' ? 'ERROR' : 'FRONTEND',
                    message: 'console.' + level + ': ' + text,
                    frontend: {
                        action: 'console_' + level,
                        text: text,
                    }
                });
            } catch (err) { /* never break the app's logging */ }
            return original.apply(console, arguments);
        };
    });

    // ---- Capture page-load performance + navigation HTTP status ----
    function capturePerformance() {
        if (!window.performance) return;

        var nav = performance.getEntriesByType('navigation')[0];
        if (!nav) return;

        var metrics = {
            domContentLoaded: Math.round(nav.domContentLoadedEventEnd - nav.startTime),
            loadComplete: Math.round(nav.loadEventEnd - nav.startTime),
            responseTime: Math.round(nav.responseEnd - nav.requestStart),
            domProcessing: Math.round(nav.domInteractive - nav.startTime),
        };

        if (metrics.loadComplete <= 0) return;

        // Full-page navigation HTTP error (where the browser exposes it)
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
        var message = 'Page load: ' + metrics.loadComplete + 'ms (DOM: ' + metrics.domContentLoaded + 'ms, Response: ' + metrics.responseTime + 'ms)';

        sendEvent({
            severity: severity,
            category: 'PERFORMANCE',
            message: message,
            frontend: {
                action: 'page_load',
                url: window.location.href,
                domContentLoaded: metrics.domContentLoaded,
                loadComplete: metrics.loadComplete,
                responseTime: metrics.responseTime,
                domProcessing: metrics.domProcessing,
            }
        });
    }

    if (document.readyState === 'complete') {
        capturePerformance();
    } else {
        window.addEventListener('load', capturePerformance);
    }

    // ---- Capture tab visibility changes ----
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
})();
