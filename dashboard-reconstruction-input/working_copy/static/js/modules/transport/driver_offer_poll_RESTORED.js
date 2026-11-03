(function () {
  'use strict';

  // Live offer poll for the Driver Workspace (D2 driver side).
  // Uses the new OfferPoller module with ETag, backoff, and visibility handling.

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

// Use the new OfferPoller module
    import('/static/js/modules/transport/offer-poller.js').then(function (module) {
      var poller = module.createOfferPoller({
        onOffers: function (res) {
          var offers = res && res.data && res.data.offers;
          if (!Array.isArray(offers)) return;
          var nextKey = refsKey(offers);
          if (nextKey !== baseline) {
            // Only a genuinely NEW offer rings: an expiry or a trip claimed
            // elsewhere only changes the set and refreshes panels silently.
            if (hasNewRef(baselineRefs, refsList(nextKey))) {
              try {
                sessionStorage.setItem(CHIME_KEY, String(Date.now()));
              } catch (e) {
                // Private mode — the refresh still happens, just without a chime.
              }
            }
            // Replace full reload with targeted panel refresh (preserves v2.5.1 state)
            if (window.refreshPanel) {
              window.refreshPanel('home');
              window.refreshPanel('trips');
            } else {
              window.location.reload(); // fallback
            }
          }
        },
      baseMs: 4000,
      maxMs: 30000
    });

    // Pause when action in flight
    var originalStart = poller.start;
    poller.start = function () {
      if (!actionInFlight()) originalStart();
    };
    
    // Check actionInFlight on each tick
    var checkTimer = setInterval(function () {
      if (actionInFlight()) {
        poller.stop();
      } else if (!document.hidden) {
        poller.start();
      }
    }, 1000);
    
    // Cleanup on unload
    window.addEventListener('beforeunload', function () {
      clearInterval(checkTimer);
      poller.stop();
    });
    
    poller.start();
  }).catch(function (err) {
    console.error('Failed to load offer-poller:', err);
  });
})();