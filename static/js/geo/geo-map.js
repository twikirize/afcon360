/* AFCON360 GEO - shared map-rendering capability (Leaflet path).
 *
 * Domain-neutral: renders geographic information supplied by the caller.
 * Encodes NO Transport/Accommodation/Events concepts (no driver, vehicle,
 * booking, trip, fare, or dispatch logic).
 *
 * Coordinate order: latitude-first everywhere, matching GeoPoint
 * ({latitude, longitude}). Leaflet consumes [lat, lng], so NO reversal
 * happens at this boundary. Callers pass {latitude, longitude} objects;
 * a latitude/longitude swap upstream is caller-visible (marker lands
 * somewhere else) rather than silently corrected here.
 *
 * Truthfulness: when the renderer cannot draw (library missing, no tile
 * URL, invalid center), the container shows an explicit message instead
 * of a blank area or a fabricated map. No fake coordinates or markers
 * are ever invented.
 */
(function () {
  'use strict';

  function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = (text === undefined || text === null) ? '' : String(text);
    return div.innerHTML;
  }

  function isFiniteNumber(value) {
    return typeof value === 'number' && isFinite(value);
  }

  function truthfulState(container, message) {
    container.setAttribute('data-geo-map-status', 'unavailable');
    container.innerHTML =
      '<div class="geo-map-fallback" role="status">' +
      '<p><strong>Map unavailable</strong></p>' +
      '<p>' + escapeHtml(message) + '</p>' +
      '</div>';
    return { status: 'unavailable', reason: message };
  }

  function init(containerId, options) {
    var container = document.getElementById(containerId);
    if (!container) {
      return { status: 'no-container' };
    }
    var opts = options || {};

    if (typeof L === 'undefined') {
      return truthfulState(
        container,
        'Map library failed to load. The rest of this page remains usable.'
      );
    }
    if (!opts.tileUrl) {
      return truthfulState(
        container,
        'Map tiles are not configured. The rest of this page remains usable.'
      );
    }

    var center = opts.center || {};
    var lat = Number(center.latitude);
    var lng = Number(center.longitude);
    if (!isFinite(lat) || !isFinite(lng)) {
      return truthfulState(
        container,
        'No map center is available. The rest of this page remains usable.'
      );
    }

    var map = L.map(container).setView(
      [lat, lng],
      opts.zoom || 12
    );
    L.tileLayer(opts.tileUrl, {
      attribution: opts.attribution || '',
      maxZoom: 19
    }).addTo(map);

    var noticeShown = false;
    map.on('tileerror', function () {
      if (noticeShown) {
        return;
      }
      noticeShown = true;
      var notice = document.createElement('p');
      notice.className = 'geo-map-tile-notice';
      notice.setAttribute('role', 'status');
      notice.textContent =
        'Map tiles are failing to load. The rest of this page remains usable.';
      container.appendChild(notice);
    });

    var markers = Array.isArray(opts.markers) ? opts.markers : [];
    markers.forEach(function (marker) {
      if (!marker) {
        return;
      }
      var mLat = Number(marker.latitude);
      var mLng = Number(marker.longitude);
      if (!isFinite(mLat) || !isFinite(mLng)) {
        return;
      }
      // Latitude-first, same order as GeoPoint - no reversal.
      var pin = L.marker([mLat, mLng]).addTo(map);
      if (marker.popup) {
        pin.bindPopup(escapeHtml(marker.popup));
      }
    });

    container.setAttribute('data-geo-map-status', 'rendered');
    var handle = {
      status: 'rendered',
      map: map,
      center: { latitude: lat, longitude: lng }
    };
    // Inspectable handle for debugging and verification consoles.
    container._geoMap = handle;
    return handle;
  }

  window.GeoMap = {
    init: init,
    version: 1
  };
})();
