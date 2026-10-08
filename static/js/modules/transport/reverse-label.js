/* AFCON360 — provider-neutral reverse-identity bridge (Discovery).
 *
 * Turns already-accepted GPS/map coordinates into a human-readable label
 * via the shared GEO endpoint contract:
 *
 *   GET /geo/api/reverse?lat=<lat>&lon=<lon>   (same-origin)
 *   -> 200 {success, provider, latitude, longitude, display_name,
 *           presentable, attribution}
 *
 * Enrichment ONLY: this module never writes coordinates, sources, or
 * evidence — callers own their location state and pass back only the
 * display string (or null when nothing trustworthy exists).
 *
 *   window.__reverseLabel(lat, lng, callback)
 *     callback(displayNameOrNull) — fires at most once per call, and
 *     only for the LATEST call (sequence guard + AbortController: a
 *     stale response never overwrites a newer location's label).
 *
 * Failure contract: any transport/provider failure, any non-presentable
 * answer, and any invalid input yields callback(null) — the caller keeps
 * its generic method label ("Current location" / "Pinned location").
 * Exactly one request is ever in flight; a newer call aborts the older.
 */
(function () {
  'use strict';

  var ENDPOINT = '/geo/api/reverse';

  var seq = 0;          // newest call wins
  var inflight = null;  // AbortController of the live request

  window.__reverseLabel = function (lat, lng, callback) {
    var mySeq = ++seq;
    if (typeof callback !== 'function') return;
    if (inflight) {
      try { inflight.abort(); } catch (e) { /* best effort */ }
      inflight = null;
    }
    var latNum = Number(lat);
    var lngNum = Number(lng);
    if (!isFinite(latNum) || !isFinite(lngNum)) {
      callback(null);
      return;
    }
    var ctrl = (typeof AbortController === 'function') ? new AbortController() : null;
    inflight = ctrl;
    fetch(ENDPOINT + '?lat=' + encodeURIComponent(latNum) +
          '&lon=' + encodeURIComponent(lngNum), {
      headers: { 'Accept': 'application/json' },
      credentials: 'same-origin',
      signal: ctrl ? ctrl.signal : undefined
    }).then(function (res) {
      if (mySeq !== seq) return null;   /* stale — drop silently */
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    }).then(function (data) {
      if (mySeq !== seq) return;        /* stale — drop silently */
      inflight = null;
      if (data && data.success === true && data.presentable === true &&
          typeof data.display_name === 'string' && data.display_name.trim() !== '') {
        callback(data.display_name);
      } else {
        callback(null);
      }
    }).catch(function () {
      if (mySeq !== seq) return;        /* aborted/stale — silent */
      inflight = null;
      callback(null);
    });
  };
})();
