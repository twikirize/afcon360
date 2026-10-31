/**
 * ThemeStore - Single owner, single-flight, subscribers
 * Avoids duplicate /theme/api/preferences calls
 */

const ThemeStore = (() => {
  let state = window.__THEME_BOOTSTRAP__ || null;
  let pending = null;
  const subs = new Set();

  function load() {
    if (state) return Promise.resolve(state);
    if (pending) return pending;
    pending = fetch('/theme/api/preferences', { credentials: 'same-origin' })
      .then(r => r.json())
      .then(d => { state = d; subs.forEach(fn => fn(d)); return d; })
      .finally(() => { pending = null; });
    return pending;
  }

  return {
    get: load,
    subscribe(fn) { subs.add(fn); state ? fn(state) : load(); return () => subs.delete(fn); },
    invalidate() { state = null; }
  };
})();

// Expose globally for ThemeManager
window.ThemeStore = ThemeStore;

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = ThemeStore;
}