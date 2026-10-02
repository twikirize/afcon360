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
  var FLAG_TTL_MS = 120000;
  var PENDING_TTL_MS = 120000;
  var COOLDOWN_MS = 8000;
  var POLL_MS = 20000;
  var UNREAD_ENDPOINT = '/api/notifications/unread-count?by_module=true';

  var audioCtx = null;
  var pendingAt = 0;
  var lastRingAt = 0;
  var baseline = null;

  // Driver-chosen alert sound (Account → Offer alert sound). Stored on the
  // device (localStorage): sound is a property of this phone's speaker, not
  // of the driver profile, so it needs no server round-trip and works
  // offline. Unknown values fall back to 'chime'. Patterns are
  // [offsetMs, freqHz, durSec, peakGain] played through tone() below.
  var SOUND_KEY = 'ck_alert_sound';
  var SOUNDS = {
    chime:  { label: 'Chime',  notes: [[0, 1046.5, 0.18, 0.16], [130, 1318.51, 0.42, 0.14]] },
    urgent: { label: 'Urgent', notes: [[0, 880, 0.15, 0.25], [180, 880, 0.15, 0.25], [360, 880, 0.15, 0.25], [540, 1174.66, 0.40, 0.25]] },
    bell:   { label: 'Bell',   notes: [[0, 523.25, 0.50, 0.22], [0, 659.25, 0.50, 0.15], [300, 783.99, 0.60, 0.18]] },
    horn:   { label: 'Horn',   notes: [[0, 392.00, 0.35, 0.22], [0, 493.88, 0.35, 0.22], [400, 392.00, 0.35, 0.22], [400, 493.88, 0.35, 0.22]] }
  };
  function selectedSound() {
    var name = null;
    try {
      name = localStorage.getItem(SOUND_KEY);
    } catch (e) {
      // storage unavailable — default sound still rings
    }
    if (name === 'custom' || SOUNDS[name]) return name;
    return 'chime';
  }

  // Driver's own sound file, picked from this phone and kept ONLY on this
  // phone (IndexedDB audio bytes + localStorage selection). Never uploaded,
  // never in our database. Unknown/missing custom file falls back to chime
  // so an alert is never silent because a file went missing.
  var customBuffer = null;
  var customLoading = false;
  function customStore(mode, fn) {
    try {
      if (!window.indexedDB) { fn(null); return; }
      var req = window.indexedDB.open('afcon-driver', 1);
      req.onupgradeneeded = function () {
        try { req.result.createObjectStore('sounds'); } catch (e) {}
      };
      req.onsuccess = function () {
        try {
          fn(req.result.transaction('sounds', mode).objectStore('sounds'));
        } catch (e) { fn(null); }
      };
      req.onerror = function () { fn(null); };
    } catch (e) { fn(null); }
  }
  var decodeSeq = 0;
  function decodeCustom(buf, then) {
    var ctx = context();
    if (!ctx || !buf) { if (then) then(false); return; }
    // Sequence guard: rapid re-picks must not let an older, slower decode
    // overwrite a newer file's buffer.
    var seq = ++decodeSeq;
    try {
      ctx.decodeAudioData(buf.slice ? buf.slice(0) : buf,
        function (ab) {
          if (seq !== decodeSeq) return;
          customBuffer = ab;
          customState = 'ready';
          if (then) then(true);
        },
        function () {
          if (seq !== decodeSeq) return;
          customBuffer = null;
          customState = 'missing';
          if (then) then(false);
        });
    } catch (e) {
      customBuffer = null;
      customState = 'missing';
      if (then) then(false);
    }
  }
  // Decode-first save: the bytes are stored only after they prove
  // playable, and the buffer is set atomically — re-picking never leaves
  // the old song playing under the new file's name.
  function prepareCustom(buf, name, ok) {
    decodeCustom(buf, function (good) {
      if (!good) { if (ok) ok(false); return; }
      saveCustom(buf, name, ok);
    });
  }
  // Three-state custom tracking: 'unknown' (not loaded yet — never wipe
  // the user's choice), 'ready' (buffer playable), 'missing' (confirmed
  // absent/unplayable — only then may the selection revert to chime).
  // A fresh page load races the first alert; ringing chime meanwhile must
  // NOT destroy the saved selection.
  var customState = 'unknown';
  function loadCustom() {
    if (customLoading && customState !== 'unknown') return;
    customLoading = true;
    customStore('readonly', function (st) {
      if (!st) return; // transient — stays unknown, retried per ring
      try {
        var g = st.get('custom');
        g.onsuccess = function () {
          var rec = g.result;
          if (rec && rec.data) {
            decodeCustom(rec.data, function (good) {
              customState = good ? 'ready' : 'missing';
              if (!good) loadBackup(function (found) {
                if (!found) customState = 'missing';
              });
            });
          } else {
            customBuffer = null;
            loadBackup(function (found) {
              if (!found) customState = 'missing';
            });
          }
        };
        g.onerror = function () {};
      } catch (e) {}
    });
  }
  function saveCustom(buf, name, ok) {
    customStore('readwrite', function (st) {
      if (!st) { if (ok) ok(false); return; }
      try {
        var req = st.put({ data: buf, name: name || '', at: Date.now() }, 'custom');
        req.onsuccess = function () {
          backupCustom(buf, name);
          decodeCustom(buf);
          if (ok) ok(true);
        };
        req.onerror = function () { if (ok) ok(false); };
      } catch (e) { if (ok) ok(false); }
    });
  }
  // Second copy of the file as base64 in localStorage. IndexedDB alone
  // proved losable across sessions on some phone browsers (choice in
  // localStorage survived while the IDB bytes did not), so the song is
  // kept in both device stores. Best-effort: quota failure keeps IDB-only.
  var BACKUP_KEY = 'ck_custom_audio';
  function backupCustom(buf, name) {
    try {
      var bytes = new Uint8Array(buf);
      var chunk = 8192;
      var bin = '';
      for (var i = 0; i < bytes.length; i += chunk) {
        bin += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
      }
      localStorage.setItem(BACKUP_KEY, JSON.stringify({
        name: name || '', at: Date.now(),
        data: btoa(bin)
      }));
    } catch (e) {}
  }
  function b64ToBytes(b64) {
    var bin = atob(b64);
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes.buffer;
  }
  function loadBackup(done) {
    var raw = null;
    try { raw = localStorage.getItem(BACKUP_KEY); } catch (e) { if (done) done(false); return; }
    if (!raw) { if (done) done(false); return; }
    try {
      var rec = JSON.parse(raw);
      if (rec && rec.data) {
        decodeCustom(b64ToBytes(rec.data), function (good) {
          if (good) customState = 'ready';
          if (done) done(good);
        });
        return;
      }
    } catch (e) {}
    if (done) done(false);
  }
  function clearCustom(ok) {
    customBuffer = null;
    customState = 'missing';
    try { localStorage.removeItem(BACKUP_KEY); } catch (e) {}
    customStore('readwrite', function (st) {
      if (!st) { if (ok) ok(false); return; }
      try {
        var req = st.delete('custom');
        req.onsuccess = function () { if (ok) ok(true); };
        req.onerror = function () { if (ok) ok(false); };
      } catch (e) { if (ok) ok(false); }
    });
  }
  // Saved-file proof for the panel: returns the stored file name (or null).
  // The file picker itself can never show it — browsers always render an
  // empty picker on load — so the panel displays this instead.
  function customName(cb) {
    var fromBackup = function () {
      try {
        var raw = localStorage.getItem(BACKUP_KEY);
        if (raw) {
          var rec = JSON.parse(raw);
          if (rec && rec.name && cb) { cb(rec.name); return; }
        }
      } catch (e) {}
      if (cb) cb(null);
    };
    customStore('readonly', function (st) {
      if (!st) { fromBackup(); return; }
      try {
        var g = st.get('custom');
        g.onsuccess = function () {
          var rec = g.result;
          if (rec && rec.name) { if (cb) cb(rec.name); } else { fromBackup(); }
        };
        g.onerror = function () { fromBackup(); };
      } catch (e) { fromBackup(); }
    });
  }
  function playCustom(ctx, maxSec) {
    try {
      stopPreview();
      var src = ctx.createBufferSource();
      src.buffer = customBuffer;
      src.connect(ctx.destination);
      src.start(0);
      // Alarm-length cap: a full song must never play for minutes. Rings
      // stay under the 6s repeat beat; previews may run longer (explicit).
      var cap = (typeof maxSec === 'number' && maxSec > 0) ? maxSec : 5;
      try { src.stop(ctx.currentTime + cap); } catch (e) {}
      previewSrc = src;
      return true;
    } catch (e) {
      return false;
    }
  }
  var previewSrc = null;
  function stopPreview() {
    // A second preview tap must stop the first: never stack songs on songs.
    if (previewSrc) {
      try { previewSrc.stop(0); } catch (e) {}
      try { previewSrc.disconnect(); } catch (e) {}
      previewSrc = null;
    }
  }

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

  function playPattern(ctx, name) {
    var notes = (SOUNDS[name] || SOUNDS.chime).notes;
    var t = ctx.currentTime + 0.02;
    notes.forEach(function (n) {
      tone(ctx, n[1], t + n[0] / 1000, n[2], n[3]);
    });
  }

  // Immediate playback for the Account-panel preview button. A preview tap
  // is itself the user gesture, so it plays even when the context starts
  // suspended. Exposed globally; the panel wires it by element id.
  function previewSound(name) {
    if (document.hidden) return false;
    var want = (name === 'custom' || SOUNDS[name]) ? name : selectedSound();
    var ctx = context();
    if (!ctx) return false;
    // A preview tap is explicit — it must not consume the anti-double-ring
    // cooldown that protects real offer alerts.
    var go = function () { playSelected(ctx, want, 30); };
    if (ctx.state !== 'running' && typeof ctx.resume === 'function') {
      try {
        var p = ctx.resume();
        if (p && typeof p.then === 'function') { p.then(go, function () {}); return true; }
      } catch (e) {
        return false;
      }
    }
    go();
    return true;
  }
  // Return the selection to the default chime when a custom file is
  // CONFIRMED unplayable (deleted data, cleared storage, failed decode).
  // Alerts degrade to chime, never to silence, and the panel reflects the
  // truth if present. Pass keepChoice=true while the file may simply not
  // have loaded yet — the saved selection must survive a slow decode.
  function revertToDefault(keepChoice) {
    if (!keepChoice) {
      try { localStorage.setItem(SOUND_KEY, 'chime'); } catch (e) {}
    }
    try {
      Array.prototype.forEach.call(
        document.querySelectorAll('input[name="alert_sound"]'),
        function (r) { r.checked = (r.value === 'chime'); });
      var st = document.getElementById('customSoundStatus');
      if (st) st.textContent = 'Saved sound unavailable — back to Chime.';
      var row = document.getElementById('customSoundRow');
      if (row) row.style.display = 'none';
    } catch (e) {}
  }
  // Play the selection, falling back to chime when a custom file is chosen
  // but not (or no longer) playable. Alerts must never go silent.
  // maxSec caps custom playback (rings stay short, previews may run long).
  function playSelected(ctx, want, maxSec) {
    var name = (want === 'custom' || SOUNDS[want]) ? want : selectedSound();
    if (name === 'custom') {
      if (customBuffer && playCustom(ctx, maxSec)) return;
      if (customState === 'unknown') {
        // Custom file not loaded YET (fresh page, slow decode) — ring chime
        // this once but keep the saved choice; retry the load for next time.
        loadCustom();
        revertToDefault(true);
        name = 'chime';
      } else {
        // Confirmed missing/unplayable — fall back and reset the choice.
        revertToDefault(false);
        name = 'chime';
      }
    }
    playPattern(ctx, name);
  }
  try {
    window.AFCONDriverSound = {
      preview: previewSound,
      selected: selectedSound,
      names: function () { return Object.keys(SOUNDS); },
      saveCustom: saveCustom,
      prepareCustom: prepareCustom,
      clearCustom: clearCustom,
      customReady: function () { return !!customBuffer; },
      customState: function () { return customState; }
    };
  } catch (e) {
    // non-browser harness — selectors below simply never bind
  }
  loadCustom();

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
    playSelected(ctx, selectedSound());
  }

  // Persistent alarm: while a live, unacted offer sits on the page, keep
  // ringing the selected sound until it is accepted, declined, or expires.
  // Expiry/claim changes the offer set, and the poll reloads the page, so
  // the alarm stops by itself. Accept/decline taps disable the buttons
  // while the POST is in flight, which pauses the alarm. Hidden tabs stay
  // silent (page audio cannot run there); the unread-count poll and the
  // reload chime still cover the return path.
  var REPEAT_MS = 6000;
  var lastRepeatAt = 0;
  function unactedOfferPresent() {
    var el = document.querySelector('[data-offer-refs]');
    if (!el) return false;
    if (!(el.getAttribute('data-offer-refs') || '').trim()) return false;
    if (document.querySelector('.offer-accept:disabled, .offer-decline:disabled')) return false;
    return true;
  }
  function repeatTick() {
    if (document.hidden) return;
    if (!unactedOfferPresent()) return;
    var now = Date.now();
    if (now - lastRepeatAt < REPEAT_MS) return;
    var ctx = context();
    if (!ctx || ctx.state !== 'running') {
      pendingAt = now;
      resume();
      return;
    }
    lastRepeatAt = now;
    lastRingAt = now;
    playSelected(ctx, selectedSound());
  }
  setInterval(repeatTick, 2000);

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
  // Returning to the app is engagement too: a reload-triggered chime that
  // landed while AudioContext was still suspended gets its resume chance
  // the moment the page becomes visible again (no tap required).
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) unlock();
  });
  window.addEventListener('focus', unlock);
  window.addEventListener('pageshow', function () { unlock(); });

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
