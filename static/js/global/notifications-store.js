/**
 * NotificationStore - Single poller, many subscribers
 * Avoids duplicate /api/notifications/unread-count calls
 */

const NotificationStore = (() => {
  let data = null, pending = null, timer = null, backoff = 20000;
  const subs = new Set();

  async function tick() {
    if (pending) return pending;
    pending = fetch('/api/notifications/unread-count?by_module=true', { credentials: 'same-origin' })
      .then(r => r.json())
      .then(d => { data = d; subs.forEach(fn => fn(d)); backoff = 20000; })
      .catch(() => { backoff = Math.min(backoff * 2, 120000); })
      .finally(() => { pending = null; schedule(); });
    return pending;
  }

  function schedule() {
    clearTimeout(timer);
    if (!document.hidden) timer = setTimeout(tick, backoff + Math.random() * 3000);
  }

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) clearTimeout(timer);
    else { backoff = 20000; tick(); }
  });

  return {
    subscribe(fn) { subs.add(fn); data ? fn(data) : tick(); return () => subs.delete(fn); },
    poke() { backoff = 20000; tick(); }
  };
})();

// Expose globally
window.NotificationStore = NotificationStore;

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = NotificationStore;
}