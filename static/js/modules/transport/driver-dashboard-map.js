/*
 * AFCON360 Driver Dashboard Map Adapter
 *
 * Uses the platform's shared Leaflet/GEO renderer. This adapter is display
 * only: driver-dashboard.js remains the sole owner of GPS acquisition and
 * server-side location publishing. The optional device-centering action
 * obtains a one-time browser position and never sends it to the server.
 */
(function () {
  'use strict';

  function finiteCoordinate(value, minimum, maximum) {
    if (value === null || value === undefined || String(value).trim() === '') {
      return null;
    }
    var number = Number(value);
    return Number.isFinite(number) && number >= minimum && number <= maximum
      ? number : null;
  }

  function setState(message, isError) {
    var state = document.getElementById('driverMapState');
    if (!state) return;
    state.textContent = message;
    state.classList.toggle('badge-amber', !!isError);
    state.classList.toggle('badge-green', false);
    state.classList.toggle('badge-gray', !isError);
  }

  function setupPlaceSearch(map, container) {
    var searchUrl = container.dataset.geocodeUrl;
    var input = document.getElementById('driverMapSearch');
    var searchButton = document.getElementById('driverMapSearchBtn');
    var resultsBox = document.getElementById('driverMapSearchResults');
    var state = document.getElementById('driverMapSearchState');
    var attribution = document.getElementById('driverMapAttribution');
    if (!input || !searchButton || !resultsBox || !state) return;

    var searchMarker = null;
    var latestResults = [];

    function setSearchState(message, isError) {
      state.textContent = message;
      state.setAttribute('aria-live', isError ? 'assertive' : 'polite');
    }

    function hideResults() {
      resultsBox.hidden = true;
      resultsBox.replaceChildren();
      latestResults = [];
    }

    function focusResult(result) {
      var latitude = finiteCoordinate(result && result.latitude, -90, 90);
      var longitude = finiteCoordinate(result && result.longitude, -180, 180);
      if (latitude === null || longitude === null || !window.L) {
        setSearchState('This search result has invalid coordinates.', true);
        return;
      }

      var label = String(result.label || 'Selected place');
      var coordinates = [latitude, longitude];
      if (searchMarker) {
        searchMarker.setLatLng(coordinates);
      } else {
        searchMarker = window.L.marker(coordinates, {
          title: 'Searched place'
        }).addTo(map);
      }
      var popupContent = document.createElement('span');
      popupContent.textContent = label;
      searchMarker.bindPopup(popupContent).openPopup();
      map.setView(coordinates, Math.max(map.getZoom(), 14));
      setSearchState('Map centered on ' + label, false);
      hideResults();
    }

    function renderResults(items) {
      hideResults();
      latestResults = items.slice(0, 5);
      latestResults.forEach(function (item, index) {
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'driver-map-search__result';
        button.setAttribute('role', 'option');
        button.textContent = String(item.label || 'Unnamed place');
        button.addEventListener('click', function () {
          focusResult(latestResults[index]);
        });
        resultsBox.appendChild(button);
      });
      resultsBox.hidden = latestResults.length === 0;
    }

    async function searchPlaces() {
      var query = input.value.trim();
      if (query.length < 2) {
        hideResults();
        if (attribution) {
          attribution.textContent = '';
          attribution.hidden = true;
        }
        setSearchState('Enter at least two characters to search.', true);
        return;
      }
      if (!searchUrl || typeof window.fetch !== 'function') {
        setSearchState('Place search is unavailable. The map is still usable.', true);
        return;
      }

      searchButton.disabled = true;
      hideResults();
      setSearchState('Searching places…', false);
      if (attribution) {
        attribution.textContent = '';
        attribution.hidden = true;
      }

      try {
        var response = await window.fetch(
          searchUrl + '?q=' + encodeURIComponent(query) + '&limit=5',
          {
            method: 'GET',
            credentials: 'same-origin',
            cache: 'no-store',
            headers: { Accept: 'application/json' }
          }
        );
        if (!response.ok) throw new Error('Place search failed');
        var payload = await response.json();
        if (!payload || payload.success !== true || !Array.isArray(payload.results)) {
          throw new Error('Invalid place search response');
        }

        var validResults = payload.results.filter(function (item) {
          return item &&
            finiteCoordinate(item.latitude, -90, 90) !== null &&
            finiteCoordinate(item.longitude, -180, 180) !== null;
        });
        if (attribution && typeof payload.attribution === 'string' && payload.attribution.trim()) {
          attribution.textContent = payload.attribution;
          attribution.hidden = false;
        }
        if (!validResults.length) {
          setSearchState('No places found. Try a town, area or nearby landmark.', false);
          return;
        }
        renderResults(validResults);
        setSearchState(validResults.length + ' place result(s). Select one to center the map.', false);
      } catch (error) {
        hideResults();
        setSearchState('Place search is unavailable right now. Try again later.', true);
      } finally {
        searchButton.disabled = false;
      }
    }

    searchButton.addEventListener('click', searchPlaces);
    input.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
        event.preventDefault();
        searchPlaces();
      } else if (event.key === 'Escape') {
        hideResults();
      }
    });
  }

  function setupDemandOverlay(map, container) {
    var demandUrl = container.dataset.demandUrl;
    var state = document.getElementById('driverDemandState');
    var refreshButton = document.getElementById('driverDemandRefreshBtn');
    var filter = document.getElementById('driverDemandFilter');
    if (!state || !refreshButton) return;

    var layer = window.L && typeof window.L.layerGroup === 'function'
      ? window.L.layerGroup().addTo(map) : null;
    var entries = [];
    var emptyStateMessage = 'No recent request clusters nearby (24h)';
    var emptyStateIsError = false;

    function setDemandState(message, isError) {
      state.textContent = message;
      state.classList.toggle('badge-amber', !!isError);
      state.classList.toggle('badge-gray', !isError);
    }

    function bandForCount(count) {
      if (count >= 10) return 'high';
      if (count >= 6) return 'medium';
      return 'low';
    }

    function applyDemandFilter() {
      if (!layer) return;
      var selected = filter ? filter.value : 'all';
      var visible = 0;
      entries.forEach(function (entry) {
        var show = selected === 'all' || bandForCount(entry.count) === selected;
        if (show) {
          layer.addLayer(entry.circle);
          visible += 1;
        } else {
          layer.removeLayer(entry.circle);
        }
      });

      if (entries.length === 0) {
        setDemandState(emptyStateMessage, emptyStateIsError);
      } else {
        var level = selected === 'all' ? 'all' : selected + ' demand';
        setDemandState(
          visible + ' of ' + entries.length + ' nearby request zones · ' + level + ' · last 24 hours',
          false
        );
      }
    }

    async function refreshDemand() {
      if (!layer || !demandUrl || typeof window.fetch !== 'function') {
        setDemandState('Recent demand map unavailable', true);
        return;
      }

      refreshButton.disabled = true;
      setDemandState('Loading recent demand…', false);
      try {
        var response = await window.fetch(demandUrl, {
          method: 'GET',
          credentials: 'same-origin',
          cache: 'no-store',
          headers: { Accept: 'application/json' }
        });
        if (!response.ok) throw new Error('Demand request failed');
        var payload = await response.json();
        if (!payload || payload.success !== true || !Array.isArray(payload.cells)) {
          throw new Error('Invalid demand response');
        }

        layer.clearLayers();
        entries = [];
        if (payload.state === 'location_unavailable') {
          emptyStateMessage = 'Waiting for a fresh driver location';
          emptyStateIsError = true;
          setDemandState(emptyStateMessage, true);
          return;
        }

        payload.cells.forEach(function (cell) {
          var center = cell && cell.center;
          var latitude = center ? Number(center.latitude) : NaN;
          var longitude = center ? Number(center.longitude) : NaN;
          var count = Number(cell && cell.request_count);
          if (!Number.isInteger(count) || count < 3 ||
              !Number.isFinite(latitude) || latitude < -90 || latitude > 90 ||
              !Number.isFinite(longitude) || longitude < -180 || longitude > 180) {
            return;
          }

          var tone = count >= 10 ? '#dc2626' : count >= 6 ? '#ea580c' : '#d97706';
          var circle = window.L.circle([latitude, longitude], {
            radius: 420,
            color: tone,
            weight: 1,
            fillColor: tone,
            fillOpacity: Math.min(0.36, 0.16 + (count / 40))
          }).bindTooltip('Booking requests in last 24 hours: ' + count, {
            direction: 'top'
          });
          entries.push({ circle: circle, count: count });
        });

        emptyStateMessage = 'No recent request clusters nearby (24h)';
        emptyStateIsError = false;
        applyDemandFilter();
      } catch (error) {
        layer.clearLayers();
        entries = [];
        emptyStateMessage = 'Recent demand unavailable; driver tools remain available';
        emptyStateIsError = true;
        setDemandState(emptyStateMessage, true);
      } finally {
        refreshButton.disabled = false;
      }
    }

    if (filter) filter.addEventListener('change', applyDemandFilter);
    refreshButton.addEventListener('click', refreshDemand);
    refreshDemand();
  }

  function boot() {
    var root = document.getElementById('driverDashboard');
    var container = document.getElementById('driverMap');
    var note = document.getElementById('driverMapNote');
    var locateButton = document.getElementById('driverMapLocateBtn');
    if (!root || !container || container.dataset.mapBooted === '1') return;
    container.dataset.mapBooted = '1';

    if (!window.GeoMap || typeof window.GeoMap.init !== 'function') {
      container.setAttribute('data-geo-map-status', 'unavailable');
      setState('Map renderer unavailable', true);
      if (note) note.textContent = 'The rest of the driver workspace remains available.';
      if (locateButton) locateButton.disabled = true;
      return;
    }

    var defaultLat = finiteCoordinate(container.dataset.defaultLat, -90, 90);
    var defaultLng = finiteCoordinate(container.dataset.defaultLng, -180, 180);
    var lastLat = finiteCoordinate(container.dataset.lastLat, -90, 90);
    var lastLng = finiteCoordinate(container.dataset.lastLng, -180, 180);
    var hasLastPosition = lastLat !== null && lastLng !== null;

    if (defaultLat === null || defaultLng === null) {
      setState('Map centre unavailable', true);
      if (note) note.textContent = 'No valid default map centre was supplied by GEO.';
      if (locateButton) locateButton.disabled = true;
      return;
    }

    var center = hasLastPosition
      ? { latitude: lastLat, longitude: lastLng }
      : { latitude: defaultLat, longitude: defaultLng };
    var markers = hasLastPosition ? [{
      latitude: lastLat,
      longitude: lastLng,
      popup: 'Last published driver position'
    }] : [];

    var handle = window.GeoMap.init('driverMap', {
      tileUrl: container.dataset.tileUrl || '',
      attribution: container.dataset.tileAttribution || '',
      center: center,
      zoom: hasLastPosition ? Math.max(14, Number(container.dataset.defaultZoom) || 12)
        : (Number(container.dataset.defaultZoom) || 12),
      markers: markers
    });

    if (!handle || handle.status !== 'rendered' || !handle.map) {
      setState('Map unavailable', true);
      if (note) note.textContent = 'Map tiles or the map library are unavailable. Driver status and GPS publishing continue independently.';
      if (locateButton) locateButton.disabled = true;
      return;
    }

    var map = handle.map;
    setupPlaceSearch(map, container);
    setupDemandOverlay(map, container);
    var deviceMarker = null;
    window.setTimeout(function () {
      try { map.invalidateSize({ pan: false }); } catch (error) { /* map may have been closed */ }
    }, 100);
    window.addEventListener('resize', function () {
      try { map.invalidateSize({ pan: false }); } catch (error) { /* map may have been closed */ }
    });

    if (hasLastPosition) {
      var timestamp = container.dataset.lastTs;
      var when = timestamp ? new Date(timestamp) : null;
      var suffix = when && !Number.isNaN(when.getTime())
        ? ' · recorded ' + when.toLocaleString() : '';
      setState('Last published position', false);
      if (note) note.textContent = 'Showing the last position saved by the dashboard' + suffix + '. It may not be the device’s current position. Tiles: ' + (container.dataset.tileSourceLabel || 'configured map source') + '.';
    } else {
      setState('Default map area', false);
      if (note) note.textContent = 'This is the default map centre, not a tracked driver location. Tiles: ' + (container.dataset.tileSourceLabel || 'configured map source') + '. The dashboard GPS publisher will report a position when it has a valid fix.';
    }

    if (locateButton) {
      locateButton.addEventListener('click', function () {
        if (!navigator.geolocation) {
          setState('Device location unavailable', true);
          if (note) note.textContent = 'This browser does not provide device geolocation.';
          return;
        }

        locateButton.disabled = true;
        setState('Getting device position…', false);
        navigator.geolocation.getCurrentPosition(function (position) {
          var latitude = position.coords.latitude;
          var longitude = position.coords.longitude;
          if (!Number.isFinite(latitude) || !Number.isFinite(longitude) ||
              latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180 ||
              !window.L) {
            setState('Device position unavailable', true);
            locateButton.disabled = false;
            return;
          }

          var coordinates = [latitude, longitude];
          if (deviceMarker) {
            deviceMarker.setLatLng(coordinates);
          } else {
            deviceMarker = window.L.marker(coordinates, {
              title: 'Current device position'
            }).addTo(map);
          }
          deviceMarker.bindPopup('Current device position (shown on this device only)');
          map.setView(coordinates, Math.max(map.getZoom(), 15));
          setState('Device position shown locally', false);
          if (note) note.textContent = 'This one-time position is only used to centre this map. Server publishing remains controlled by the dashboard GPS service.';
          locateButton.disabled = false;
        }, function (error) {
          var message = error && error.code === 1
            ? 'Location permission denied'
            : error && error.code === 3
              ? 'Device location timed out'
              : 'Device location unavailable';
          setState(message, true);
          if (note) note.textContent = 'Allow location access in the browser and try again. The dashboard can continue without the map.';
          locateButton.disabled = false;
        }, {
          enableHighAccuracy: true,
          timeout: 12000,
          maximumAge: 30000
        });
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
