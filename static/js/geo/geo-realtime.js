/* AFCON360 GEO - shared realtime location client (SSE path).
 *
 * Domain-neutral: delivers geographic events to a caller-supplied handler.
 * Encodes NO Transport/Accommodation/Events concepts (no driver, vehicle,
 * booking, trip, fare, dispatch, online, or availability logic). Freshness
 * facts (fresh/stale/missing/disconnected/degraded) are geographic recency
 * only - operational meaning stays with the owning domain.
 *
 * Contract:
 *   GeoRealtime.connect(streamUrl, { onSnapshot, onLocation, onState })
 *     -> { close(), state }.
 * Events carry {latitude, longitude} (latitude-first, GeoPoint order).
 * A latitude/longitude swap upstream is consumer-visible, never corrected.
 *
 * Reconnect: the server sends `retry:` and every stream opens with the
 * current snapshot, so EventSource auto-reconnect recovers latest state
 * with no replay. Consecutive-error bounding prevents retry storms:
 * after MAX_ERRORS errors the client closes and reports `disconnected`.
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
      accuracy: toFinite(data.accuracy) || 0,
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
    var handle = {
      state: 'connecting',
      close: function () {
        closed = true;
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
      } else if (status === 'closed') {
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
        return handle;
      }
      source = new EventSource(streamUrl);
    } catch (e) {
      emitState('disconnected', { reason: 'event-source-failed' });
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
        handle.close();
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
