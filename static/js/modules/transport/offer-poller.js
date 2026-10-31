/**
 * OfferPoller - Single-flight, ETag, backoff, visibility-aware
 * Replaces the naive setInterval in driver_offer_poll.js
 */

export function createOfferPoller({ onOffers, baseMs = 4000, maxMs = 30000 }) {
  let timer = null, cur = baseMs, running = false, pending = null, etag = null;
  let wasRunning = false; // track if we were explicitly stopped

  async function tick() {
    if (!running) return;
    if (pending) return pending;
    const headers = etag ? { 'If-None-Match': etag } : {};
    pending = fetch('/api/transport/drivers/me/offers', {
      credentials: 'same-origin',
      headers
    })
      .then(res => {
        if (res.status === 304) return null;
        etag = res.headers.get('ETag') || null;
        return res.json();
      })
      .then(res => {
        if (!res) return;
        const n = (res.offers || []).length;
        onOffers(res);
        cur = n > 0 ? baseMs : Math.min(cur * 2, maxMs); // back off when idle
      })
      .catch(() => { cur = Math.min(cur * 2, maxMs); })
      .finally(() => { pending = null; schedule(); });
    return pending;
  }

  function schedule() {
    clearTimeout(timer);
    if (running) timer = setTimeout(tick, cur + Math.random() * 600);
  }

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      stop();
    } else if (!wasRunning) {
      // Only reset backoff on visibility change if we weren't explicitly running before
      start();
    }
  });

  function start() { 
    if (!running) { 
      running = true; 
      wasRunning = true;
      // Only reset cur if we were explicitly stopped (not just hidden)
      tick(); 
    } 
  }
  
  function stop() { 
    running = false; 
    wasRunning = false;
    clearTimeout(timer); 
  }

  return { start, stop, poke() { cur = baseMs; tick(); } };
}