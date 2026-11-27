/* AFCON360 Transport — rider road-route preview.
 *
 * Sends only resolved endpoint coordinates to the same-origin Transport API.
 * The browser never talks directly to Valhalla and never calculates road
 * distance. Fare quote and booking behavior remain owned by their existing
 * server-side paths.
 */
(function () {
  'use strict';

  var summary = document.getElementById('roadRouteSummary');
  var title = document.getElementById('roadRouteSummaryTitle');
  var note = document.getElementById('roadRouteSummaryNote');
  var retryButton = document.getElementById('roadRouteRetry');
  var form = document.getElementById('boltForm');

  if (!summary || !title || !note || !form) return;

  var endpoint = summary.getAttribute('data-endpoint') || '';
  var csrfField = form.querySelector('input[name="csrf_token"]');
  var debounceTimer = null;
  var inflight = null;
  var sequence = 0;
  var lastCoordinatesKey = null;

  var fields = {
    pickupLatitude: document.getElementById('pickup_latitude'),
    pickupLongitude: document.getElementById('pickup_longitude'),
    dropoffLatitude: document.getElementById('dropoff_latitude'),
    dropoffLongitude: document.getElementById('dropoff_longitude')
  };

  function finiteCoordinate(field, bound) {
    if (!field || field.value.trim() === '') return null;
    var value = Number(field.value);
    if (!isFinite(value) || value < -bound || value > bound) return null;
    return value;
  }

  function readCoordinates() {
    var pickupLatitude = finiteCoordinate(fields.pickupLatitude, 90);
    var pickupLongitude = finiteCoordinate(fields.pickupLongitude, 180);
    var dropoffLatitude = finiteCoordinate(fields.dropoffLatitude, 90);
    var dropoffLongitude = finiteCoordinate(fields.dropoffLongitude, 180);

    if (pickupLatitude === null || pickupLongitude === null ||
        dropoffLatitude === null || dropoffLongitude === null) {
      return null;
    }

    return {
      pickup_latitude: pickupLatitude,
      pickup_longitude: pickupLongitude,
      dropoff_latitude: dropoffLatitude,
      dropoff_longitude: dropoffLongitude
    };
  }

  function clearRenderedRoute() {
    if (typeof window.__mapClearRoadRoute === 'function') {
      window.__mapClearRoadRoute();
    }
  }

  function setState(state, heading, detail) {
    summary.hidden = state === 'idle';
    summary.setAttribute('data-route-state', state);
    title.textContent = heading || '';
    note.textContent = detail || '';
    if (retryButton) retryButton.hidden = state !== 'unavailable';
  }

  function cancelInflight() {
    if (!inflight) return;
    try { inflight.abort(); } catch (err) { /* best effort */ }
    inflight = null;
  }

  function formatDuration(durationSeconds) {
    var totalMinutes = Math.max(0, Math.round(Number(durationSeconds) / 60));
    var hours = Math.floor(totalMinutes / 60);
    var minutes = totalMinutes % 60;
    if (hours && minutes) return hours + 'h ' + minutes + 'm';
    if (hours) return hours + 'h';
    return totalMinutes + ' min';
  }

  function validGeometry(geometry) {
    if (!Array.isArray(geometry) || geometry.length === 0) return false;
    return geometry.every(function (point) {
      if (!point || typeof point !== 'object') return false;
      var lat = Number(point.latitude);
      var lng = Number(point.longitude);
      return isFinite(lat) && isFinite(lng) &&
        lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180;
    });
  }

  function showUnavailable(message) {
    clearRenderedRoute();
    setState(
      'unavailable',
      'Driving route unavailable',
      message || 'We could not calculate a road route right now. You can still review fare options.'
    );
  }

  function requestPreview(payload, mySequence) {
    if (!endpoint) {
      showUnavailable('The route-preview service is not configured on this page.');
      return;
    }

    var controller = (typeof AbortController === 'function')
      ? new AbortController() : null;
    inflight = controller;

    var headers = {
      'Accept': 'application/json',
      'Content-Type': 'application/json'
    };
    if (csrfField && csrfField.value) {
      headers['X-CSRFToken'] = csrfField.value;
    }

    fetch(endpoint, {
      method: 'POST',
      headers: headers,
      credentials: 'same-origin',
      body: JSON.stringify(payload),
      signal: controller ? controller.signal : undefined
    }).then(function (response) {
      if (mySequence !== sequence) return null;
      return response.json().then(function (body) {
        if (!response.ok) {
          var error = new Error('Route preview HTTP ' + response.status);
          error.payload = body;
          throw error;
        }
        return body;
      });
    }).then(function (body) {
      if (mySequence !== sequence || body === null) return;
      inflight = null;

      var data = body && body.success === true ? body.data : null;
      if (!data || data.resolved !== true ||
          !isFinite(Number(data.distance_m)) || Number(data.distance_m) < 0 ||
          !isFinite(Number(data.duration_s)) || Number(data.duration_s) < 0 ||
          !validGeometry(data.geometry)) {
        showUnavailable();
        return;
      }

      var rendered = (typeof window.__mapRenderRoadRoute === 'function') &&
        window.__mapRenderRoadRoute(data.geometry);

      var distanceKm = (Number(data.distance_m) / 1000).toFixed(1);
      var duration = formatDuration(data.duration_s);
      setState(
        'resolved',
        'Driving route · ' + distanceKm + ' km · ' + duration,
        rendered
          ? 'Planned road route. Fare calculation continues to use the existing separate pricing basis.'
          : 'Road measurements resolved, but the map could not display the route geometry.'
      );
    }).catch(function (error) {
      if (mySequence !== sequence) return;
      inflight = null;
      if (error && error.name === 'AbortError') return;
      showUnavailable();
    });
  }

  function schedulePreview(force) {
    var payload = readCoordinates();
    if (!payload) {
      sequence += 1;
      lastCoordinatesKey = null;
      if (debounceTimer) {
        window.clearTimeout(debounceTimer);
        debounceTimer = null;
      }
      cancelInflight();
      clearRenderedRoute();
      setState('idle', '', '');
      return;
    }

    var coordinatesKey = JSON.stringify(payload);
    if (!force && coordinatesKey === lastCoordinatesKey) return;
    lastCoordinatesKey = coordinatesKey;

    sequence += 1;
    var mySequence = sequence;

    if (debounceTimer) {
      window.clearTimeout(debounceTimer);
      debounceTimer = null;
    }
    cancelInflight();

    clearRenderedRoute();
    setState(
      'loading',
      'Calculating driving route…',
      'The road route is informational; it does not change your fare.'
    );

    debounceTimer = window.setTimeout(function () {
      debounceTimer = null;
      requestPreview(payload, mySequence);
    }, 250);
  }

  document.addEventListener('afcon360:route-preview-inputs-changed', function () {
    schedulePreview(false);
  });

  // Allow explicit retry after a provider/network failure without changing
  // either endpoint selection or the existing ride-options flow.
  if (retryButton) {
    retryButton.addEventListener('click', function () {
      schedulePreview(true);
    });
  }

  // Keep the initial state hidden until the existing page script validates
  // both pickup and destination and emits its coordinate-change event.
  setState('idle', '', '');
})();
