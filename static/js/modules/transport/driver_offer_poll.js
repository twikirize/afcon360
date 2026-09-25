(function () {
  'use strict';

  // Live offer poll for the Driver Workspace (D2 driver side).
  // The server renders offers on page load; this beats the
  // GET /api/transport/drivers/me/offers endpoint and reloads only when
  // the SET of live offer refs actually changed (offer arrived, expired,
  // or was claimed elsewhere) so the focus card + badge stay truthful
  // without a websocket. Reload is skipped while an accept/decline POST
  // is in flight (button disabled) or the tab is hidden.

  var ENDPOINT = '/api/transport/drivers/me/offers';
  var INTERVAL_MS = 4000;
  // Key read by driver_alerts.js, which rings AFTER the reload (a reload
  // would cut any sound started before it).
  var CHIME_KEY = 'ck_offer_chime';

  function readBaseline() {
    var el = document.querySelector('[data-offer-refs]');
    if (!el) return null;
    return (el.getAttribute('data-offer-refs') || '').trim();
  }

  function refsKey(offers) {
    return offers
      .map(function (o) { return o && o.booking_reference ? o.booking_reference : ''; })
      .filter(Boolean)
      .sort()
      .join(',');
  }

  function refsList(key) {
    return (key || '').split(',').filter(Boolean);
  }

  function hasNewRef(before, after) {
    var seen = {};
    before.forEach(function (r) { seen[r] = 1; });
    return after.some(function (r) { return !seen[r]; });
  }

  function actionInFlight() {
    return !!document.querySelector('.offer-accept:disabled, .offer-decline:disabled');
  }

  var baseline = readBaseline();
  if (baseline === null) return;
  var baselineRefs = refsList(baseline);

  setInterval(function () {
    if (actionInFlight() || document.hidden) return;
    fetch(ENDPOINT, {
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json' }
    })
      .then(function (r) {
        if (!r.ok) throw new Error('offer poll status ' + r.status);
        return r.json();
      })
      .then(function (body) {
        var offers = body && body.data && body.data.offers;
        if (!Array.isArray(offers)) return;
        var nextKey = refsKey(offers);
        if (nextKey !== baseline) {
          // Only a genuinely NEW offer rings: an expiry or a trip claimed
          // elsewhere only changes the set and reloads silently.
          if (hasNewRef(baselineRefs, refsList(nextKey))) {
            try {
              sessionStorage.setItem(CHIME_KEY, String(Date.now()));
            } catch (e) {
              // Private mode — the reload still happens, just without a chime.
            }
          }
          window.location.reload();
        }
      })
      .catch(function () {
        // Transient store/network failure — retry on the next beat.
      });
  }, INTERVAL_MS);
})();
