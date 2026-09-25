(function () {
  'use strict';

  // Driver Workspace alert layer (D2 driver side).
  //
  // Two audible triggers, one cooldown so a single event never rings twice:
  //   1. NEW live offer — driver_offer_poll.js stamps sessionStorage just
  //      before it reloads on a changed offer set; a reload would cut any
  //      sound started before it, so the ring happens after the page lands.
  //   2. Inbox count up — transport notifications (trip assigned, status
  //      change, …) read from /api/notifications/unread-count, the same
  //      source the bell paints its badge from.
  //
  // The chime is synthesised with WebAudio: no media file to ship, nothing
  // to 404, nothing for CSP media-src, and it keeps working offline.
  //
  // Persistence stays server-side (app/notifications): every driver
  // notification is a durable row, so the bell panel and
  // /notifications?module=transport remain the place to read them once the
  // sound has stopped.

  var CHIME_KEY = 'ck_offer_chime';
  var FLAG_TTL_MS = 60000;
  var PENDING_TTL_MS = 15000;
  var COOLDOWN_MS = 8000;
  var POLL_MS = 20000;
  var UNREAD_ENDPOINT = '/api/notifications/unread-count?by_module=true';

  var audioCtx = null;
  var pendingAt = 0;
  var lastRingAt = 0;
  var baseline = null;

  function context() {
    if (audioCtx) return audioCtx;
    var Ctor = window.AudioContext || window.webkitAudioContext;
    if (!Ctor) return null;
    try {
      audioCtx = new Ctor();
    } catch (e) {
      audioCtx = null;
    }
    return audioCtx;
  }

  // Resume is asynchronous and a fresh context reports 'suspended' until the
  // gesture lands, so playback is chained onto the resume promise instead of
  // being read back synchronously (which silently drops the chime).
  function resume(then) {
    var ctx = context();
    if (!ctx || ctx.state === 'running' || typeof ctx.resume !== 'function') {
      if (then) then();
      return;
    }
    var fired = false;
    var finish = function () {
      if (fired) return;
      fired = true;
      if (then) then();
    };
    try {
      var p = ctx.resume();
      if (p && typeof p.then === 'function') {
        p.then(finish, function () {});
        return;
      }
    } catch (e) {
      // Autoplay still blocked — the next gesture retries.
    }
    finish();
  }

  function tone(ctx, freq, at, dur, peak) {
    var osc = ctx.createOscillator();
    var gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(freq, at);
    gain.gain.setValueAtTime(0.0001, at);
    gain.gain.exponentialRampToValueAtTime(peak, at + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + dur);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(at);
    osc.stop(at + dur + 0.02);
  }

  function ring() {
    if (document.hidden) return;
    var now = Date.now();
    if (now - lastRingAt < COOLDOWN_MS) return;
    var ctx = context();
    if (!ctx) {
      // No WebAudio yet (blocked or unsupported at this moment) — retry
      // from the next gesture instead of losing the alert.
      pendingAt = now;
      return;
    }
    if (ctx.state !== 'running') {
      pendingAt = now;
      resume();
      return;
    }
    lastRingAt = now;
    var t = ctx.currentTime + 0.02;
    tone(ctx, 1046.5, t, 0.18, 0.16);         // C6
    tone(ctx, 1318.51, t + 0.13, 0.42, 0.14); // E6
  }

  function flushPending() {
    if (!pendingAt) return;
    if (Date.now() - pendingAt > PENDING_TTL_MS) {
      pendingAt = 0;
      return;
    }
    pendingAt = 0;
    ring();
  }

  function unlock() {
    resume(flushPending);
  }

  ['pointerdown', 'keydown', 'touchend'].forEach(function (evt) {
    document.addEventListener(evt, unlock, true);
  });

  function paintBadges(total, byModule) {
    var roots = document.querySelectorAll('.afc-notif');
    Array.prototype.forEach.call(roots, function (root) {
      var mod = root.getAttribute('data-module');
      var count = mod ? (byModule[mod] || 0) : (total || 0);
      var badge = root.querySelector('.afc-notif__badge');
      if (!badge) return;
      badge.setAttribute('data-count', String(count));
      badge.textContent = count < 100 ? String(count) : '99+';
      badge.classList.toggle('is-hidden', !count);
    });
  }

  function poll() {
    if (document.hidden) return;
    fetch(UNREAD_ENDPOINT, {
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json' }
    })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) return;
        var byModule = d.unread_by_module || {};
        var transportCount = byModule.transport || 0;
        paintBadges(d.unread_count || 0, byModule);
        // First response only sets the watermark — entering the workspace
        // with unread items already there must not ring.
        if (baseline === null) {
          baseline = transportCount;
          return;
        }
        if (transportCount > baseline) ring();
        baseline = transportCount;
      })
      .catch(function () {
        // Offline or transient failure — the next beat retries.
      });
  }

  poll();
  setInterval(poll, POLL_MS);

  // Offer chime left behind by driver_offer_poll.js before its reload.
  try {
    var stamped = sessionStorage.getItem(CHIME_KEY);
    if (stamped) {
      sessionStorage.removeItem(CHIME_KEY);
      var at = parseInt(stamped, 10) || 0;
      if (at && Date.now() - at < FLAG_TTL_MS) ring();
    }
  } catch (e) {
    // Storage unavailable — nothing to replay.
  }
})();
