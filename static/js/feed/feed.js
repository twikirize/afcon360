/* =============================================================
   AFCON360 — Feed JS (static/js/feed/feed.js)

   - IntersectionObserver-based infinite scroll
   - Fetches /api/home/feed?page=N&seed=S&layout=L
   - Renders items via JS template (mirrors _item_card.html)
   - Tab switching for tabbed layout (client-side filter, no re-fetch)
   - Admin layout toggle handler

   The feed container (#feed-container) has data attributes:
     data-layout, data-seed, data-next-page, data-has-more
   ============================================================= */
(function () {
  'use strict';

  // ── Item renderer (mirrors templates/feed/_item_card.html) ─────
  function escapeHtml(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function formatExtras(metadata, type) {
    if (!metadata) return '';
    var extras = [];
    if (type === 'event') {
      if (metadata.start_date) extras.push(extra('📅', metadata.start_date.slice(0, 10)));
      if (metadata.city) extras.push(extra('📍', metadata.city + (metadata.country ? ', ' + metadata.country : '')));
      if (metadata.venue) extras.push(extra('🏟', metadata.venue));
      if (metadata.registration_fee) extras.push(extra('💵', metadata.registration_fee + ' ' + (metadata.currency || 'USD')));
      if (metadata.featured) extras.push(highlight('⭐ Featured'));
    } else if (type === 'property') {
      if (metadata.property_type) extras.push(extra('🏠', metadata.property_type));
      if (metadata.city) extras.push(extra('📍', metadata.city + (metadata.country ? ', ' + metadata.country : '')));
      if (metadata.price_per_night) extras.push(extra('💵', metadata.price_per_night + '/night'));
    } else if (type === 'transport') {
      if (metadata.route_type) extras.push(extra('', metadata.route_type));
      if (metadata.primary_zone) extras.push(extra('📍', metadata.primary_zone));
      if (metadata.price_per_seat) extras.push(extra('💵', metadata.price_per_seat + '/seat'));
      if (metadata.available_seats) extras.push(extra('🪑', metadata.available_seats + ' seats'));
    } else if (type === 'post') {
      if (metadata.likes != null) extras.push(extra('❤', metadata.likes));
      if (metadata.comments != null) extras.push(extra('💬', metadata.comments));
    } else if (type === 'system_update') {
      if (metadata.module_label) extras.push(highlight(metadata.module_label));
    }
    if (!extras.length) return '';
    return '<div class="feed-item-extras">' + extras.join('') + '</div>';
  }

  function extra(icon, text) {
    return '<span class="feed-extra">' + (icon ? icon + ' ' : '') + escapeHtml(text) + '</span>';
  }
  function highlight(text) {
    return '<span class="feed-extra feed-extra-highlight">' + escapeHtml(text) + '</span>';
  }

  function typeIcon(type) {
    var icons = {
      post: '💬', event: '🏟️', ad: '📣', system_update: '🔔',
      property: '🏨', transport: '🚌'
    };
    return icons[type] || '📰';
  }

  function renderItem(item) {
    var html = '<article class="feed-item feed-type-' + escapeHtml(item.type) +
      (item.is_pinned ? ' is-pinned' : '') +
      '" data-feed-id="' + escapeHtml(item.feed_id) +
      '" data-type="' + escapeHtml(item.type) + '">';

    if (item.is_pinned) {
      html += '<span class="feed-pin-badge">📌 Pinned</span>';
    }

    // Header
    html += '<header class="feed-item-head">';
    html += '<span class="feed-item-icon feed-icon-' + escapeHtml(item.type) + '">' + typeIcon(item.type) + '</span>';
    html += '<div class="feed-item-meta">';
    html += '<span class="feed-item-author">' + escapeHtml(item.author_name || 'AFCON360') + '</span>';
    if (item.source_module) {
      html += '<span class="feed-item-module">' + escapeHtml(item.source_module.charAt(0).toUpperCase() + item.source_module.slice(1)) + '</span>';
    }
    html += '</div>';
    if (item.type === 'ad') {
      html += '<span class="feed-sponsored-tag">Sponsored</span>';
    }
    html += '</header>';

    // Body
    html += '<div class="feed-item-body">';
    if (item.title) {
      html += '<h3 class="feed-item-title">' + escapeHtml(item.title) + '</h3>';
    }
    if (item.body) {
      html += '<p class="feed-item-text">' + escapeHtml(item.body) + '</p>';
    }
    if (item.image_url) {
      html += '<div class="feed-item-image-wrap">' +
        '<img src="' + escapeHtml(item.image_url) + '" alt="' + escapeHtml(item.title || '') + '" loading="lazy" ' +
        'onerror="this.parentElement.style.display=\'none\'"></div>';
    }
    html += formatExtras(item.metadata, item.type);
    html += '</div>';

    // Footer
    if (item.link_url) {
      html += '<footer class="feed-item-foot">' +
        '<a href="' + escapeHtml(item.link_url) + '" class="feed-item-link">View Details →</a>' +
        '</footer>';
    }

    html += '</article>';
    return html;
  }

  // ── Infinite Scroll Controller ────────────────────────────────
  var container = document.getElementById('feed-container');
  if (!container) return;

  var layout = container.getAttribute('data-layout') || 'mixed';
  var seed = container.getAttribute('data-seed') || '';
  var nextPage = parseInt(container.getAttribute('data-next-page') || '2', 10);
  var hasMore = container.getAttribute('data-has-more') === 'true';
  var stream = document.getElementById('feed-stream');
  var sentinel = document.getElementById('feed-sentinel');
  var spinner = document.getElementById('feed-loading-spinner');
  var endMessage = document.getElementById('feed-end-message');
  var loading = false;

  function loadMore() {
    if (loading || !hasMore) return;
    loading = true;
    if (spinner) spinner.style.display = 'inline-block';

    var url = '/api/home/feed?page=' + nextPage + '&per_page=10&layout=' + encodeURIComponent(layout) + '&seed=' + encodeURIComponent(seed);

    fetch(url, { headers: { 'Accept': 'application/json' }, credentials: 'same-origin' })
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        if (data.items && data.items.length) {
          data.items.forEach(function (item) {
            if (layout === 'tabbed') {
              // Wrap in tab wrapper div
              var wrapper = document.createElement('div');
              wrapper.className = 'feed-tab-wrapper';
              wrapper.setAttribute('data-type', item.type);
              // Respect current active tab
              var activeTab = document.querySelector('.feed-tab.is-active');
              if (activeTab && activeTab.getAttribute('data-tab') !== 'all' && activeTab.getAttribute('data-tab') !== item.type) {
                wrapper.className = 'feed-tab-wrapper is-hidden';
              }
              wrapper.innerHTML = renderItem(item);
              stream.appendChild(wrapper);
            } else {
              stream.insertAdjacentHTML('beforeend', renderItem(item));
            }
          });
        }
        nextPage++;
        hasMore = data.has_more;
        if (!hasMore) {
          if (spinner) spinner.style.display = 'none';
          if (endMessage) endMessage.style.display = 'inline-block';
        }
      })
      .catch(function (err) {
        console.error('Feed load error:', err);
      })
      .finally(function () {
        loading = false;
        if (spinner) spinner.style.display = 'none';
      });
  }

  // IntersectionObserver on sentinel
  if (sentinel && 'IntersectionObserver' in window) {
    var observer = new IntersectionObserver(function (entries) {
      if (entries[0].isIntersecting && hasMore && !loading) {
        loadMore();
      }
    }, { rootMargin: '200px' });
    observer.observe(sentinel);
  } else if (sentinel) {
    // Fallback: scroll listener
    window.addEventListener('scroll', function () {
      var rect = sentinel.getBoundingClientRect();
      if (rect.top < window.innerHeight + 200 && hasMore && !loading) {
        loadMore();
      }
    });
  }

  // ── Tab switching (tabbed layout) ──────────────────────────────
  var tabBar = document.getElementById('feed-tabs');
  if (tabBar) {
    tabBar.addEventListener('click', function (e) {
      var tab = e.target.closest('.feed-tab');
      if (!tab) return;
      // Update active state
      var allTabs = tabBar.querySelectorAll('.feed-tab');
      allTabs.forEach(function (t) { t.classList.remove('is-active'); });
      tab.classList.add('is-active');
      // Filter items
      var filterType = tab.getAttribute('data-tab');
      var wrappers = stream.querySelectorAll('.feed-tab-wrapper');
      wrappers.forEach(function (w) {
        if (filterType === 'all' || w.getAttribute('data-type') === filterType) {
          w.classList.remove('is-hidden');
        } else {
          w.classList.add('is-hidden');
        }
      });
    });
  }

  // ── Admin Layout Toggle ────────────────────────────────────────
  var toggleForm = document.getElementById('feed-layout-toggle-form');
  if (toggleForm) {
    toggleForm.addEventListener('submit', function (e) {
      e.preventDefault();
      var select = document.getElementById('feed-layout-select');
      if (!select) return;
      var btn = toggleForm.querySelector('button[type="submit"]');
      var originalText = btn ? btn.textContent : '';
      if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }

      fetch('/api/home/feed/layout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCSRFToken(),
        },
        credentials: 'same-origin',
        body: JSON.stringify({ layout: select.value })
      })
        .then(function (resp) { return resp.json(); })
        .then(function (data) {
          if (data.status === 'ok') {
            if (btn) btn.textContent = '✓ Saved';
            setTimeout(function () { window.location.reload(); }, 800);
          } else {
            alert(data.message || 'Failed to save layout');
            if (btn) { btn.disabled = false; btn.textContent = originalText; }
          }
        })
        .catch(function (err) {
          console.error('Layout toggle error:', err);
          alert('Failed to save layout');
          if (btn) { btn.disabled = false; btn.textContent = originalText; }
        });
    });
  }

  function getCSRFToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }
})();
