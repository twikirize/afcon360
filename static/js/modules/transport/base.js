// Base transport module JavaScript
// Shared delegated behaviours for transport driver-facing pages.
//
// Uses event delegation (single document listener) so buttons added after
// DOM ready (e.g. client-side filtering) still work — no re-binding needed.

(function () {
  'use strict';

  function csrfMeta() {
    return document.head.querySelector('meta[name="csrf-token"]');
  }

  function csrfHeaders() {
    var meta = csrfMeta();
    var headers = { 'Content-Type': 'application/json' };
    if (meta) {
      headers['X-CSRFToken'] = meta.getAttribute('content');
    }
    return headers;
  }

  function flashMsg(message, ok) {
    var box = document.createElement('div');
    box.className = 'alert alert-' + (ok ? 'green' : 'red');
    box.style.margin = '0 16px 16px';
    box.innerHTML =
      '<i class="fa-solid fa-' + (ok ? 'circle-check' : 'circle-exclamation') + '"></i>' +
      '<span style="flex:1;">' + message + '</span>' +
      '<button onclick="this.parentElement.remove()" class="alert-close"><i class="fa-solid fa-xmark"></i></button>';
    var main = document.querySelector('.t-content');
    if (main) {
      main.prepend(box);
    }
  }

  /* Request a contract for a marketplace vehicle.
   *
   * The driver acts as themselves (current_user server-side); no id or plate
   * is read from the button. The only data the button carries is the
   * server-built request URL (data-url) and a display name for cosmetic
   * messages — the internal vehicle id never reaches the page (AGENTS §12.1).
   */
  function requestVehicle(btn) {
    var url = btn.getAttribute('data-url');
    var name = btn.getAttribute('data-vehicle-name') || 'this vehicle';
    if (!url) {
      flashMsg('Missing request URL', false);
      return;
    }
    if (!window.confirm('Request a contract to drive ' + name + '? The owner will review your application.')) {
      return;
    }
    var prev = btn.innerHTML;
    var prevDisabled = btn.disabled;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    fetch(url, {
      method: 'POST',
      headers: csrfHeaders(),
      body: '{}'
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (d) {
        btn.disabled = prevDisabled;
        btn.innerHTML = prev;
        if (d && d.success) {
          flashMsg(d.message || 'Contract request sent to the vehicle owner', true);
        } else {
          flashMsg((d && d.error) || 'Could not send contract request', false);
        }
      })
      .catch(function () {
        btn.disabled = prevDisabled;
        btn.innerHTML = prev;
        flashMsg('Could not send contract request', false);
      });
  }

  document.addEventListener('click', function (e) {
    var btn = e.target && e.target.closest ? e.target.closest('.request-vehicle') : null;
    if (btn) {
      e.preventDefault();
      requestVehicle(btn);
    }
  });
})();
