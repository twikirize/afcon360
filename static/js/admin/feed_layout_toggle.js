// Feed layout toggle for admin/owner dashboards.
// Attaches to any element with id `feed-layout-toggle-form` + `feed-layout-select`.
(function () {
  function getCSRFToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  document.addEventListener('DOMContentLoaded', function () {
    var toggleForm = document.getElementById('feed-layout-toggle-form');
    if (!toggleForm) return;

    toggleForm.addEventListener('submit', function (e) {
      e.preventDefault();
      var select = document.getElementById('feed-layout-select');
      if (!select) return;

      var btn = toggleForm.querySelector('button[type="submit"]');
      var originalText = btn ? btn.textContent : '';
      var status = document.getElementById('feed-layout-status');
      if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
      if (status) status.textContent = 'Saving…';

      fetch('/api/home/feed/layout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCSRFToken()
        },
        credentials: 'same-origin',
        body: JSON.stringify({ layout: select.value })
      })
        .then(function (resp) { return resp.json(); })
        .then(function (data) {
          if (data.status === 'ok') {
            if (btn) btn.textContent = '✓ Saved';
            if (status) status.textContent = 'Saved: ' + select.value;
            setTimeout(function () { window.location.reload(); }, 800);
          } else {
            if (btn) { btn.disabled = false; btn.textContent = originalText; }
            if (status) status.textContent = data.message || 'Failed to save';
            alert(data.message || 'Failed to save layout');
          }
        })
        .catch(function (err) {
          console.error('Layout toggle error:', err);
          if (btn) { btn.disabled = false; btn.textContent = originalText; }
          if (status) status.textContent = 'Error saving';
          alert('Failed to save layout');
        });
    });
  });
})();
