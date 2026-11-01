/* AFCON360 GEO - shared realtime location client (SSE path).
 *
 * Domain-neutral: delivers geographic events to a caller-supplied handler.
 * Encodes NO Transport/Accommodation/Events concepts (no driver, vehicle,
 * booking, trip, fare, dispatch, online, or availability logic). Freshness
 * facts (fresh/stale/missing/disconnected/degraded) are geographic recency
 * only - operational meaning stays with the owning domain.
 *
 * Contract:
 *   GeoRealtime.connect(streamUrl, {
 *     onSnapshot, onLocation, onState, pollUrl?, pollIntervalMs?
 *   }) -> { close(), state }.
 * Events carry {latitude, longitude} (latitude-first, GeoPoint order).
 * A latitude/longitude swap upstream is consumer-visible, never corrected.
 *
 * Reconnect: the server sends `retry:` and every stream opens with the
 * current snapshot, so EventSource auto-reconnect recovers latest state
 * with no replay. Consecutive-error bounding prevents retry storms:
 * after MAX_ERRORS errors the SSE channel closes. When the caller supplies
 * an authorized same-origin `pollUrl`, bounded HTTP snapshots take over;
 * closing the returned handle stops both transports.
 */
(function () {
  'use strict';

  var MAX_ERRORS = 3;

  function toFinite(value) {
    var n = Number(value);
    return isFinite(n) ? n : null;
  }

  function normalizeEvent(data) {
    if (!data || typeof data !== 'object') {
      return null;
    }
    var lat = toFinite(data.latitude);
    var lng = toFinite(data.longitude);
    if (lat === null || lng === null) {
      return null;
    }
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
      return null;
    }
    return {
      entityType: data.entity_type || '',
      publicRef: data.public_ref || '',
      latitude: lat,
      longitude: lng,
      accuracy: (data.accuracy === null || data.accuracy === undefined)
        ? null : toFinite(data.accuracy),
      observedAt: data.observed_at || '',
      ageS: toFinite(data.age_s),
      fresh: data.fresh === true,
      source: data.source || ''
    };
  }

  function connect(streamUrl, handlers) {
    var opts = handlers || {};
    var source = null;
    var errors = 0;
    var closed = false;
    var pollUrl = opts.pollUrl || null;
    var pollIntervalMs = Math.max(3000, Number(opts.pollIntervalMs) || 5000);
    var pollTimer = null;
    var pollController = null;
    var polling = false;
    var pollErrors = 0;
    var handle = {
      state: 'connecting',
      close: function () {
        closed = true;
        stopPolling();
        if (source) {
          try {
            source.close();
          } catch (e) {
            /* already gone */
          }
          source = null;
        }
        setState('disconnected');
      }
    };

    function emitState(state, detail) {
      handle.state = state;
      if (typeof opts.onState === 'function') {
        try {
          opts.onState(state, detail || {});
        } catch (e) {
          /* caller errors must not break the stream */
        }
      }
    }

    function setState(state) {
      emitState(state, {});
    }

    function stopPolling() {
      polling = false;
      if (pollTimer) {
        clearTimeout(pollTimer);
        pollTimer = null;
      }
      if (pollController) {
        try { pollController.abort(); } catch (e) { /* already complete */ }
        pollController = null;
      }
    }

    function schedulePolling(delay) {
      if (!polling || closed || !pollUrl) return;
      if (pollTimer) clearTimeout(pollTimer);
      pollTimer = setTimeout(pollTick, delay);
    }

    function pollTick() {
      if (!polling || closed || !pollUrl || pollController) return;
      var controller = (typeof AbortController !== 'undefined')
        ? new AbortController() : null;
      pollController = controller;
      var timeout = setTimeout(function () {
        if (controller) controller.abort();
      }, 10000);
      var request = fetch(pollUrl, {
        method: 'GET',
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' },
        signal: controller ? controller.signal : undefined
      });
      request.then(function (response) {
        var contentType = response.headers && response.headers.get
          ? (response.headers.get('Content-Type') || '') : '';
        var isJson = /^application\/(?:[a-z0-9.+-]+\+)?json\b/i.test(contentType);
        if (response.redirected || response.status === 401) {
          var authRequired = new Error('tracking session expired');
          authRequired.permanent = true;
          authRequired.terminalState = 'auth-required';
          throw authRequired;
        }
        if (response.status === 403) {
          var accessDenied = new Error('tracking access denied');
          accessDenied.permanent = true;
          accessDenied.terminalState = 'access-denied';
          throw accessDenied;
        }
        if (!isJson || response.status === 404) {
          var unavailable = new Error('tracking snapshot is not available');
          unavailable.permanent = true;
          unavailable.terminalState = 'unavailable';
          throw unavailable;
        }
        if (!response.ok) throw new Error('snapshot ' + response.status);
        return response.json();
      }).then(function (payload) {
        clearTimeout(timeout);
        pollController = null;
        if (!polling || closed) return;
        var data = payload && payload.data;
        if (data && data.status === 'closed') {
          stopPolling();
          closed = true;
          if (source) {
            try { source.close(); } catch (e) { /* already gone */ }
            source = null;
          }
          emitState('closed', data);
          return;
        }
        if (data && data.status === 'missing') {
          emitState('missing', data);
        } else {
          handlePayload(data, 'snapshot');
        }
        pollErrors = 0;
        schedulePolling(pollIntervalMs);
      }).catch(function (error) {
        clearTimeout(timeout);
        pollController = null;
        if (!polling || closed) return;
        if (error && error.permanent) {
          stopPolling();
          closed = true;
          var terminalState = error.terminalState || 'unavailable';
          var reason = terminalState === 'auth-required'
            ? 'tracking-session-expired'
            : terminalState === 'access-denied'
              ? 'tracking-access-denied'
              : 'tracking-snapshot-unavailable';
          emitState(terminalState, { reason: reason });
          return;
        }
        pollErrors += 1;
        var backoff = Math.min(pollIntervalMs * Math.pow(2, pollErrors - 1), 30000);
        emitState('degraded', { reason: 'http-snapshot-unavailable',
          retry_in_ms: backoff });
        schedulePolling(backoff);
      });
    }

    function startPolling() {
      if (!pollUrl || closed || polling) return;
      polling = true;
      pollErrors = 0;
      emitState('degraded', { reason: 'sse-unavailable',
        fallback: 'http-snapshot', interval_ms: pollIntervalMs });
      schedulePolling(0);
    }

    function handlePayload(data, kind) {
      var event = normalizeEvent(data);
      if (!event) {
        return;
      }
      errors = 0;
      emitState(event.fresh ? 'fresh' : 'stale', event);
      try {
        if (kind === 'snapshot' && typeof opts.onSnapshot === 'function') {
          opts.onSnapshot(event);
        } else if (kind === 'location' && typeof opts.onLocation === 'function') {
          opts.onLocation(event);
        }
      } catch (e) {
        /* caller errors must not break the stream */
      }
    }

    function handleStateFrame(data) {
      errors = 0;
      var status = (data && data.status) || 'missing';
      if (status === 'degraded') {
        emitState('degraded', data);
        startPolling();
      } else if (status === 'closed') {
        stopPolling();
        // Booking-scoped streams close when tracking authorization ends
        // (terminal state, released assignment). Terminal: do not retry.
        try {
          if (source) {
            source.close();
          }
        } catch (e) {
          /* already gone */
        }
        closed = true;
        source = null;
        emitState('closed', data);
      } else {
        emitState('missing', data);
      }
      if (typeof opts.onState === 'function') {
        // state already emitted above; nothing further to do
      }
    }

    try {
      if (typeof EventSource === 'undefined') {
        emitState('unsupported', {});
        startPolling();
        return handle;
      }
      source = new EventSource(streamUrl);
    } catch (e) {
      emitState('disconnected', { reason: 'event-source-failed' });
      startPolling();
      return handle;
    }

    source.addEventListener('snapshot', function (e) {
      var data = null;
      try {
        data = JSON.parse(e.data);
      } catch (err) {
        return;
      }
      handlePayload(data, 'snapshot');
    });

    source.addEventListener('location', function (e) {
      var data = null;
      try {
        data = JSON.parse(e.data);
      } catch (err) {
        return;
      }
      handlePayload(data, 'location');
    });

    source.addEventListener('state', function (e) {
      var data = {};
      try {
        data = JSON.parse(e.data);
      } catch (err) {
        /* fall through with empty state */
      }
      handleStateFrame(data);
    });

    source.onerror = function () {
      if (closed) {
        return;
      }
      errors += 1;
      if (errors >= MAX_ERRORS) {
        if (source) {
          try { source.close(); } catch (e) { /* already gone */ }
          source = null;
        }
        emitState('disconnected', { attempt: errors,
          reason: 'sse-retry-budget-exhausted' });
        startPolling();
        return;
      }
      emitState('reconnecting', { attempt: errors, maxAttempts: MAX_ERRORS });
    };

    return handle;
  }

  window.GeoRealtime = {
    connect: connect,
    version: 1
  };
})();
