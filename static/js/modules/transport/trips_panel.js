(function () {
  'use strict';

  var panel = document.getElementById('tripsPanel');
  if (!panel || panel.__tripsBound) {
    return;
  }
  panel.__tripsBound = true;

  function buildUrl(params) {
    var base = panel.getAttribute('data-list-url') || window.location.pathname;
    var url = new URL(base, window.location.origin);
    url.searchParams.set('_pane', '1');
    Object.keys(params || {}).forEach(function (key) {
      var value = params[key];
      if (value === null || value === undefined || value === '') {
        url.searchParams.delete(key);
      } else {
        url.searchParams.set(key, value);
      }
    });
    return url.pathname + url.search;
  }

  function fetchFragment(params) {
    return fetch(buildUrl(params), {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin'
    }).then(function (res) {
      if (!res.ok) {
        throw new Error('Request failed (' + res.status + ')');
      }
      return res.text();
    }).then(function (html) {
      var doc = new DOMParser().parseFromString(html, 'text/html');
      var next = doc.getElementById('tripsPanel');
      if (!next) {
        throw new Error('Malformed pane response');
      }
      return next;
    });
  }

  function showError(message) {
    var err = panel.querySelector('.trips-error');
    if (err) {
      err.textContent = message;
      err.hidden = false;
    }
  }

  function clearError() {
    var err = panel.querySelector('.trips-error');
    if (err) {
      err.hidden = true;
      err.textContent = '';
    }
  }

  function syncUrl(q, page) {
    try {
      var url = new URL(window.location.href);
      if (url.searchParams.has('view')) {
        return;
      }
      if (q) {
        url.searchParams.set('q', q);
      } else {
        url.searchParams.delete('q');
      }
      if (page && page > 1) {
        url.searchParams.set('page', String(page));
      } else {
        url.searchParams.delete('page');
      }
      history.replaceState(null, '', url.pathname + url.search + url.hash);
    } catch (e) {
      /* URL sync is best-effort only */
    }
  }

  panel.addEventListener('submit', function (ev) {
    var form = ev.target;
    if (!form || !form.classList || !form.classList.contains('trips-search')) {
      return;
    }
    ev.preventDefault();
    clearError();
    var input = form.querySelector('input[name="q"]');
    var q = (input ? input.value : '').trim();
    var btn = form.querySelector('button[type="submit"]');
    if (btn) {
      btn.disabled = true;
    }
    fetchFragment({ q: q, page: 1 }).then(function (next) {
      panel.innerHTML = next.innerHTML;
      panel.setAttribute('data-q', next.getAttribute('data-q') || q);
      panel.setAttribute('data-page', next.getAttribute('data-page') || '1');
      syncUrl(panel.getAttribute('data-q'), 1);
    }).catch(function () {
      if (btn) {
        btn.disabled = false;
      }
      showError('Search failed. Please try again.');
    });
  });

  panel.addEventListener('click', function (ev) {
    var target = ev.target && ev.target.closest ? ev.target : null;
    if (!target) {
      return;
    }

    var clearLink = target.closest('.trips-search a');
    if (clearLink && panel.contains(clearLink)) {
      ev.preventDefault();
      clearError();
      fetchFragment({ q: '', page: 1 }).then(function (next) {
        panel.innerHTML = next.innerHTML;
        panel.setAttribute('data-q', next.getAttribute('data-q') || '');
        panel.setAttribute('data-page', next.getAttribute('data-page') || '1');
        syncUrl('', 1);
      }).catch(function () {
        showError('Could not clear the search. Please try again.');
      });
      return;
    }

    var btn = target.closest('.trips-load-more');
    if (!btn || !panel.contains(btn)) {
      return;
    }
    ev.preventDefault();
    clearError();
    var current = parseInt(panel.getAttribute('data-page'), 10) || 1;
    var nextPage = parseInt(btn.getAttribute('data-next-page'), 10) || (current + 1);
    var q = panel.getAttribute('data-q') || '';
    btn.disabled = true;
    btn.textContent = 'Loading…';
    fetchFragment({ q: q, page: nextPage }).then(function (next) {
      var curList = panel.querySelector('#pastList');
      var nextList = next.querySelector('#pastList');
      if (curList && nextList) {
        if (curList.querySelector('.trips-note')) {
          curList.innerHTML = '';
        }
        Array.prototype.slice.call(nextList.children).forEach(function (node) {
          curList.appendChild(node);
        });
      }
      var curMore = panel.querySelector('.trips-more');
      var nextMore = next.querySelector('.trips-more');
      if (curMore) {
        if (nextMore) {
          curMore.replaceWith(nextMore);
        } else {
          curMore.remove();
        }
      }
      panel.setAttribute('data-page', next.getAttribute('data-page') || String(nextPage));
      syncUrl(q, parseInt(panel.getAttribute('data-page'), 10) || 1);
    }).catch(function () {
      btn.disabled = false;
      btn.textContent = 'Load more past trips';
      showError('Could not load more trips. Please try again.');
    });
  });
})();
