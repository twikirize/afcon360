/* AFCON360 GEO - shared map-rendering capability (Leaflet path).
 *
 * Domain-neutral: renders geographic information supplied by the caller.
 * Encodes NO Transport/Accommodation/Events concepts.
 *
 * Public contract:
 *   window.GeoMap.init(containerId, options)
 *   -> {
 *        status: 'rendered',
 *        map,
 *        tileLayer,
 *        center,
 *        zoom,
 *        retry(),
 *        destroy()
 *      }
 *   -> {status: 'unavailable', reason: '...'}
 *   -> {status: 'no-container'}
 *
 * Coordinate order:
 *   latitude-first everywhere.
 *   Leaflet consumes [lat, lng].
 *   No coordinate reversal or silent correction occurs here.
 *
 * Truthfulness:
 *   If the map cannot render, the container receives an explicit
 *   unavailable state. No fabricated coordinates or markers are created.
 *
 * Lifecycle:
 *   Any previous AFCON360 map instance in the same container is destroyed
 *   before a new initialization attempt. This prevents orphan maps,
 *   duplicate listeners/layers, and stale callbacks during retry.
 *
 * Tile degradation:
 *   The tileerror listener is attached to the TileLayer BEFORE addTo(map).
 *   A tile-error marks the current tile-loading cycle degraded.
 *   A later clean tile-loading cycle may clear the degraded state.
 */
(function () {
  'use strict';

  var VERSION = 2;

  function escapeHtml(value) {
    var div = document.createElement('div');
    div.textContent =
      (value === undefined || value === null) ? '' : String(value);
    return div.innerHTML;
  }

  /*
   * Accept numeric values and numeric strings because callers may receive
   * coordinates from JSON or form fields.
   *
   * Explicitly reject:
   *   null
   *   undefined
   *   booleans
   *   empty strings
   *
   * This prevents JavaScript coercion from turning invalid values into
   * apparently valid coordinates.
   */
  function finiteNumber(value) {
    if (value === null || value === undefined) {
      return null;
    }

    if (typeof value === 'boolean') {
      return null;
    }

    if (typeof value === 'string' && value.trim() === '') {
      return null;
    }

    if (typeof value !== 'number' && typeof value !== 'string') {
      return null;
    }

    var number = Number(value);

    return isFinite(number) ? number : null;
  }

  function validLatitude(value) {
    var number = finiteNumber(value);

    return (
      number !== null &&
      number >= -90 &&
      number <= 90
    ) ? number : null;
  }

  function validLongitude(value) {
    var number = finiteNumber(value);

    return (
      number !== null &&
      number >= -180 &&
      number <= 180
    ) ? number : null;
  }

  function validZoom(value) {
    var number = finiteNumber(value);

    if (number === null) {
      return 12;
    }

    return Math.max(0, Math.min(19, number));
  }

  function removeCurrentMap(container) {
    var existing = container && container._geoMap;

    if (!existing) {
      return;
    }

    try {
      if (typeof existing.destroy === 'function') {
        existing.destroy();
      } else if (
        existing.map &&
        typeof existing.map.remove === 'function'
      ) {
        existing.map.remove();
      }
    } catch (err) {
      /*
       * Cleanup is best-effort.
       * It must never prevent truthful reinitialization.
       */
    }

    /*
     * Destroy normally removes this itself. Keep this defensive cleanup
     * for older/foreign handles.
     */
    if (container._geoMap === existing) {
      try {
        delete container._geoMap;
      } catch (err2) {
        container._geoMap = null;
      }
    }
  }

  function clearMapStateAttributes(container) {
    container.removeAttribute('data-geo-map-status');
    container.removeAttribute('data-geo-map-tiles');
  }

  function renderUnavailable(container, message, retryFn) {
    removeCurrentMap(container);

    container.setAttribute('data-geo-map-status', 'unavailable');
    container.removeAttribute('data-geo-map-tiles');

    container.innerHTML =
      '<div class="geo-map-fallback" role="status">' +
        '<p><strong>Map unavailable</strong></p>' +
        '<p>' + escapeHtml(message) + '</p>' +
      '</div>';

    if (typeof retryFn === 'function') {
      var retryButton = document.createElement('button');
      retryButton.type = 'button';
      retryButton.className = 'geo-map-retry';
      retryButton.textContent = 'Try again';

      retryButton.addEventListener('click', function () {
        retryFn();
      });

      var fallback = container.querySelector('.geo-map-fallback');

      if (fallback) {
        fallback.appendChild(retryButton);
      }
    }

    return {
      status: 'unavailable',
      reason: message
    };
  }

  function renderTileDegraded(container, state) {
    if (!state.active || state.tileNoticeShown) {
      return;
    }

    state.tileNoticeShown = true;

    container.setAttribute('data-geo-map-tiles', 'degraded');

    var notice = document.createElement('div');
    notice.className = 'geo-map-tile-notice';
    notice.setAttribute('role', 'status');

    var text = document.createElement('p');
    text.textContent =
      'Map tiles are failing to load. The rest of this page remains usable.';
    notice.appendChild(text);

    var retryButton = document.createElement('button');
    retryButton.type = 'button';
    retryButton.className = 'geo-map-retry';
    retryButton.textContent = 'Try again';

    retryButton.addEventListener('click', function () {
      if (state.active && typeof state.retry === 'function') {
        state.retry();
      }
    });

    notice.appendChild(retryButton);
    container.appendChild(notice);
  }

  function renderTileRecovered(container, state) {
    if (!state.active || state.tileCycleHadError) {
      return;
    }

    container.removeAttribute('data-geo-map-tiles');

    var notice = container.querySelector('.geo-map-tile-notice');

    if (notice) {
      notice.remove();
    }

    state.tileNoticeShown = false;
  }

  function addMarkers(map, markers) {
    if (!Array.isArray(markers)) {
      return;
    }

    markers.forEach(function (marker) {
      if (!marker) {
        return;
      }

      var latitude = validLatitude(marker.latitude);
      var longitude = validLongitude(marker.longitude);

      if (latitude === null || longitude === null) {
        return;
      }

      try {
        /*
         * Latitude-first.
         * Do not reverse or "repair" caller coordinates.
         */
        var pin = L.marker([latitude, longitude]).addTo(map);

        if (
          marker.popup !== undefined &&
          marker.popup !== null &&
          String(marker.popup).trim() !== ''
        ) {
          pin.bindPopup(escapeHtml(marker.popup));
        }
      } catch (err) {
        /*
         * One malformed marker must not destroy an otherwise usable map.
         */
      }
    });
  }

  function init(containerId, options) {
    var container = document.getElementById(containerId);

    if (!container) {
      return {
        status: 'no-container'
      };
    }

    var opts = options || {};

    function retryInit() {
      init(containerId, opts);
    }

    /*
     * Replace any previous AFCON360 instance cleanly.
     */
    removeCurrentMap(container);
    clearMapStateAttributes(container);
    container.innerHTML = '';

    if (typeof L === 'undefined') {
      return renderUnavailable(
        container,
        'Map library failed to load. The rest of this page remains usable.',
        retryInit
      );
    }

    if (
      typeof opts.tileUrl !== 'string' ||
      opts.tileUrl.trim() === ''
    ) {
      return renderUnavailable(
        container,
        'Map tiles are not configured. The rest of this page remains usable.',
        retryInit
      );
    }

    var center = opts.center || {};

    var latitude = validLatitude(center.latitude);
    var longitude = validLongitude(center.longitude);

    if (latitude === null || longitude === null) {
      return renderUnavailable(
        container,
        'No valid map center is available. The rest of this page remains usable.',
        retryInit
      );
    }

    var zoom = validZoom(opts.zoom);

    var map = null;
    var tileLayer = null;

    var state = {
      active: true,
      tileNoticeShown: false,
      tileCycleHadError: false,
      retry: retryInit
    };

    try {
      map = L.map(container).setView(
        [latitude, longitude],
        zoom
      );

      /*
       * IMPORTANT:
       *
       * 1. Create TileLayer.
       * 2. Register tile listeners.
       * 3. Only then call addTo(map).
       *
       * This ensures early tile failures are observable.
       */
      tileLayer = L.tileLayer(opts.tileUrl, {
        attribution: opts.attribution || '',
        maxZoom: 19
      });

      tileLayer.on('loading', function () {
        if (!state.active) {
          return;
        }

        /*
         * New loading cycle starts clean.
         * A failure in this cycle will set this true again.
         */
        state.tileCycleHadError = false;
      });

      tileLayer.on('tileerror', function () {
        if (!state.active) {
          return;
        }

        state.tileCycleHadError = true;
        renderTileDegraded(container, state);
      });

      tileLayer.on('load', function () {
        /*
         * Leaflet can emit load after failed tiles have completed.
         * Do not clear a degraded state from a cycle that experienced
         * an error.
         */
        renderTileRecovered(container, state);
      });

      tileLayer.addTo(map);

      addMarkers(map, opts.markers);
    } catch (err) {
      state.active = false;

      try {
        if (map && typeof map.remove === 'function') {
          map.remove();
        }
      } catch (cleanupError) {
        /*
         * Truthful unavailable state remains the primary outcome.
         */
      }

      return renderUnavailable(
        container,
        'Map could not be started. The rest of this page remains usable.',
        retryInit
      );
    }

    var handle = {
      status: 'rendered',
      map: map,
      tileLayer: tileLayer,

      center: {
        latitude: latitude,
        longitude: longitude
      },

      zoom: zoom,

      retry: function () {
        retryInit();
      },

      destroy: function () {
        if (!state.active) {
          return;
        }

        state.active = false;

        try {
          if (
            tileLayer &&
            typeof tileLayer.remove === 'function'
          ) {
            tileLayer.remove();
          }
        } catch (err) {
          /*
           * Continue to map cleanup.
           */
        }

        try {
          if (
            map &&
            typeof map.remove === 'function'
          ) {
            map.remove();
          }
        } catch (err2) {
          /*
           * Best-effort cleanup.
           */
        }

        if (container._geoMap === handle) {
          try {
            delete container._geoMap;
          } catch (err3) {
            container._geoMap = null;
          }
        }
      }
    };

    /*
     * Existing verification/debugging contract.
     */
    container._geoMap = handle;

    container.setAttribute('data-geo-map-status', 'rendered');
    container.removeAttribute('data-geo-map-tiles');

    return handle;
  }

  window.GeoMap = {
    init: init,
    version: VERSION
  };
})();