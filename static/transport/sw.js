// AFCON360 Driver PWA — service worker.
// Network-first for /transport/ and /static/ (same-origin GET only).
// Freshness comes from the network; the cache is a fallback for offline.
const CACHE_NAME = 'afcon360-driver-v1';

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((key) => key.startsWith('afcon360-driver-') && key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      );
      await self.clients.claim();
    })()
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;

  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // Never intercept cross-origin (CDN) loads.
  if (url.origin !== self.location.origin) return;

  // Only same-origin /transport/ and /static/ paths.
  if (!url.pathname.startsWith('/transport/') && !url.pathname.startsWith('/static/')) {
    return;
  }

  // Dev escape hatch: ?nosw=1 bypasses the SW cache entirely.
  if (url.searchParams.get('nosw') === '1') return;

  event.respondWith(
    (async () => {
      try {
        const response = await fetch(request);
        if (response && response.ok) {
          const cache = await caches.open(CACHE_NAME);
          cache.put(request, response.clone());
        }
        return response;
      } catch (err) {
        const cached = await caches.match(request);
        if (cached) return cached;
        return new Response(
          '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Offline</title></head>' +
          '<body style="font-family:sans-serif;padding:24px;"><h2>You are offline</h2>' +
          '<p>This page is not available without a connection.</p></body></html>',
          { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
        );
      }
    })()
  );
});
