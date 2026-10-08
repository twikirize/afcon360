/* AFCON360 UI-01 — rider pickup typed search.
 *
 * Consumes the shared GEO endpoint contract (implemented by the server
 * side of UI-01):
 *
 *   GET /geo/api/geocode?q=<query>   (same-origin, @login_required)
 *   -> 200 {success, query, provider, results:[{label, latitude, longitude,
 *            provider, osm_type, osm_id}]}
 *   -> results may be [] (truthful miss: show "No matches", invent nothing).
 *
 * Scope — PICKUP ONLY.  This module does not implement destination search,
 * does not touch #btnLocate/GPS, does not alter map tap-to-place, and does
 * not change pricing/ride-options/matching.
 *
 * On selection it writes, mirroring the GPS handler:
 *   #inputPickup        <- result.label  (label is the canonical snapshot text)
 *   #pickup_latitude    <- result.latitude
 *   #pickup_longitude   <- result.longitude
 *   #pickup_source      <- 'search'
 *   #pickup_geocode     <- JSON.stringify(result)   (verbatim evidence echo
 *                          so the server can rehydrate a GeocodeResult)
 *   window.__mapPinPickup(lat, lng, label, 'search') when the map exists,
 *   then window.__boltValidateA() (one-line inline bridge) for revalidation.
 *
 * Truthfulness (H2):
 *   - coordinates are ONLY ever written from a server-provided result that
 *     passes a finite range check; nothing is fabricated on any failure;
 *   - a manual keystroke clears #pickup_geocode so stale evidence cannot
 *     ride along (coords + pickup_source are cleared by the existing inline
 *     input handler via __mapClearSide);
 *   - stale fetches are cancelled (sequence guard + AbortController) so an
 *     old response can never overwrite a newer query's list;
 *   - network error -> transient "Search unavailable" note, prior pickup
 *     state kept intact.
 *
 * CSP/accessibility: external nonce'd script, no inline handlers, rows are
 * built with textContent only (no innerHTML with provider data), listbox
 * uses role=listbox/option with ArrowUp/Down + Enter + Escape, touch rows
 * are >= 44px, and the dropdown is width-constrained (no horizontal
 * overflow).
 */
(function () {
  'use strict';

  var ENDPOINT = '/geo/api/geocode';
  var DEBOUNCE_MS = 300;    // implementation constant, not a contract value
  var MIN_QUERY_LEN = 2;    // mirrors the server contract: len<2 is an
                            // honest no-result with zero provider traffic
  var BLUR_HIDE_MS = 150;   // keeps an option mousedown/click reachable

  var input    = document.getElementById('inputPickup');
  var wrap     = document.getElementById('pickupSearch');
  var list     = document.getElementById('pickupResults');
  var note     = document.getElementById('pickupSearchNote');
  var geoField = document.getElementById('pickup_geocode');
  var btnSwap  = document.getElementById('btnSwap');

  if (!input || !wrap || !list || !note) return;

  var searchSeq   = 0;   // sequence guard — stale responses never render
  var debounceTimer = null;
  var blurTimer     = null;
  var inflight      = null;   // AbortController of the live request
  var results       = [];     // last rendered server results, verbatim
  var activeIndex   = -1;

  /* ---------------- guards ---------------- */

  /* A result is usable only when it carries a label and finite, in-range
   * coordinates.  Anything else is refused rather than coerced: the UI must
   * never present coordinates that did not come from the provider. */
  function validResult(r) {
    if (!r || typeof r.label !== 'string' || r.label.trim() === '') {
      return false;
    }
    var lat = Number(r.latitude);
    var lng = Number(r.longitude);
    return isFinite(lat) && isFinite(lng) &&
           lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180;
  }

  /* ---------------- list rendering ---------------- */

  function hideList() {
    wrap.classList.remove('is-open');
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    activeIndex = -1;
  }

  function showList() {
    wrap.classList.add('is-open');
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
  }

  function setNote(message) {
    if (message) {
      note.textContent = message;
      note.hidden = false;
    } else {
      note.textContent = '';
      note.hidden = true;
    }
  }

  function showUnavailable() {
    /* Transient hint only — prior pickup state stays untouched.
     * Keep the wrapper open/rendered so the note is visible, but collapse the list. */
    list.hidden = true;
    wrap.classList.add('is-open');
    input.setAttribute('aria-expanded', 'false');
    activeIndex = -1;
    setNote('Search unavailable');
  }

  function makeRow(id, text, isEmpty) {
    var row = document.createElement('div');
    row.className = 'pickup-search-option' + (isEmpty ? ' is-empty' : '');
    row.id = id;
    row.setAttribute('role', 'option');
    row.setAttribute('aria-selected', 'false');
    if (isEmpty) {
      row.setAttribute('aria-disabled', 'true');
      row.setAttribute('data-index', '-1');
    }
    row.textContent = text;          /* textContent only — never innerHTML */
    row.title = text;
    return row;
  }

  function render(items) {
    var valid = [];
    for (var i = 0; i < items.length; i++) {
      if (validResult(items[i])) valid.push(items[i]);
    }
    if (items.length && !valid.length) {
      /* Provider answered with nothing usable: truthful unavailable state. */
      showUnavailable();
      return;
    }

    results = valid;
    activeIndex = -1;
    input.removeAttribute('aria-activedescendant');
    while (list.firstChild) list.removeChild(list.firstChild);

    if (!results.length) {
      /* Non-interactive empty state — coordinates are never invented. */
      list.appendChild(makeRow('pickup-opt-empty', 'No matches', true));
      showList();
      return;
    }

    for (var j = 0; j < results.length; j++) {
      var row = makeRow('pickup-opt-' + j, results[j].label, false);
      row.setAttribute('data-index', String(j));
      list.appendChild(row);
    }
    showList();
  }

  function setActive(index) {
    activeIndex = index;
    var opts = list.querySelectorAll('[data-index]');
    for (var k = 0; k < opts.length; k++) {
      var i = Number(opts[k].getAttribute('data-index'));
      var on = i === index;
      opts[k].classList.toggle('is-active', on);
      opts[k].setAttribute('aria-selected', on ? 'true' : 'false');
      if (on) {
        input.setAttribute('aria-activedescendant', opts[k].id);
        if (opts[k].scrollIntoView) {
          opts[k].scrollIntoView({ block: 'nearest' });
        }
      }
    }
    if (index < 0) input.removeAttribute('aria-activedescendant');
  }

  function moveActive(delta) {
    if (!results.length) return;
    var next = activeIndex + delta;
    if (next < 0) next = results.length - 1;
    if (next >= results.length) next = 0;
    setActive(next);
  }

  /* ---------------- selection ---------------- */

  function selectResult(result) {
    if (!validResult(result)) {
      showUnavailable();
      return;
    }
    var lat = Number(result.latitude);
    var lng = Number(result.longitude);

    input.value = result.label;
    var latField = document.getElementById('pickup_latitude');
    var lngField = document.getElementById('pickup_longitude');
    var srcField = document.getElementById('pickup_source');
    if (latField) latField.value = String(lat);
    if (lngField) lngField.value = String(lng);
    if (srcField) srcField.value = 'search';
    /* Verbatim evidence echo — the server rehydrates the GeocodeResult
     * from this exact object (contract: JSON.stringify of the selection). */
    if (geoField) geoField.value = JSON.stringify(result);

    hideList();
    setNote('');

    /* Keep the map truthful: pin carries 'search' provenance, and the
     * existing placePin/syncCoords path re-writes coords + source from the
     * pin (validateA runs inside that path too). */
    if (window.__mapPinPickup) {
      window.__mapPinPickup(lat, lng, result.label, 'search');
    }
    /* Map may be unavailable — revalidate through the inline bridge. */
    if (window.__boltValidateA) window.__boltValidateA();
  }

  /* ---------------- search ---------------- */

  function cancelInflight() {
    if (inflight) {
      try { inflight.abort(); } catch (e) { /* best effort */ }
      inflight = null;
    }
  }

  function runSearch(text, mySeq) {
    if (mySeq !== searchSeq) return;
    var ctrl = (typeof AbortController === 'function') ? new AbortController() : null;
    inflight = ctrl;
    fetch(ENDPOINT + '?q=' + encodeURIComponent(text), {
      headers: { 'Accept': 'application/json' },
      credentials: 'same-origin',
      signal: ctrl ? ctrl.signal : undefined
    }).then(function (res) {
      if (mySeq !== searchSeq) return null;   /* stale — drop silently */
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    }).then(function (data) {
      if (mySeq !== searchSeq) return;        /* stale — drop silently */
      inflight = null;
      if (!data || data.success !== true || !Array.isArray(data.results)) {
        showUnavailable();
        return;
      }
      render(data.results);
    }).catch(function () {
      if (mySeq !== searchSeq) return;        /* aborted/stale — silent */
      inflight = null;
      showUnavailable();
    });
  }

  function scheduleSearch() {
    var text = input.value.trim();
    searchSeq += 1;                           /* sequence guard */
    var mySeq = searchSeq;
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; }
    cancelInflight();
    if (text.length < MIN_QUERY_LEN) {
      hideList();
      setNote('');
      return;
    }
    debounceTimer = setTimeout(function () {
      debounceTimer = null;
      runSearch(text, mySeq);
    }, DEBOUNCE_MS);
  }

  /* ---------------- listeners ---------------- */

  /* Registered while the document is still loading (this file is included
   * before the inline page script), so these listeners attach first and
   * complement — never replace — the inline handlers. */
  function init() {
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-controls', list.id);
    input.setAttribute('aria-expanded', 'false');

    input.addEventListener('input', function () {
      /* A real keystroke invalidates a prior selection's evidence.
       * Coords + pickup_source are already cleared by the inline handler
       * (invalidateGpsRequest + __mapClearSide); the evidence echo must
       * not remain either. */
      if (geoField) geoField.value = '';
      scheduleSearch();
    });

    input.addEventListener('keydown', function (e) {
      if (list.hidden) return;   /* list closed — inline handlers own keys */
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        moveActive(1);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        moveActive(-1);
      } else if (e.key === 'Enter') {
        /* Consume Enter while the list is open so the inline handler does
         * not jump a stage mid-search.  stopImmediatePropagation because
         * both listeners sit on the same target (ours registered first). */
        e.preventDefault();
        e.stopImmediatePropagation();
        if (activeIndex >= 0 && results[activeIndex]) {
          selectResult(results[activeIndex]);
        } else {
          hideList();
        }
      } else if (e.key === 'Escape') {
        e.preventDefault();
        hideList();
      }
    });

    input.addEventListener('focus', function () {
      if (blurTimer) { clearTimeout(blurTimer); blurTimer = null; }
    });

    input.addEventListener('blur', function () {
      /* Small delay so an option mousedown/click lands before dismissal. */
      if (blurTimer) clearTimeout(blurTimer);
      blurTimer = setTimeout(function () {
        blurTimer = null;
        hideList();
      }, BLUR_HIDE_MS);
    });

    /* Keep focus in the input while the pointer interacts with rows. */
    list.addEventListener('mousedown', function (e) {
      e.preventDefault();
    });

    list.addEventListener('click', function (e) {
      var el = e.target;
      if (!el || !el.getAttribute) return;
      var raw = el.getAttribute('data-index');
      if (raw === null) return;
      var i = Number(raw);
      if (i >= 0 && results[i]) selectResult(results[i]);
      /* data-index="-1" ("No matches") is non-interactive by design. */
    });

    if (btnSwap) {
      btnSwap.addEventListener('click', function () {
        /* Evidence fields swap in the inline swap handler; this module only
         * owns its transient list state, which belongs to the OLD pickup. */
        hideList();
        setNote('');
        results = [];
        activeIndex = -1;
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
