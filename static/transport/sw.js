/**
 * AFCON360 Transport
 * Production Secure Service Worker
 *
 * Version: 2.0.4
 *
 * SECURITY GUARANTEES:
 * 1. Never cache authenticated HTML.
 * 2. Never cache API responses or CSRF tokens.
 * 3. Cache only approved public same-origin static assets.
 * 4. Never cache non-GET requests.
 * 5. Preserve caches belonging to other applications.
 * 6. Never cache private, sensitive or redirected resources.
 * 7. Never bypass Flask authentication or authorization.
 *
 * STRATEGY:
 * HTML       -> Network first, offline fallback
 * APIs       -> Network only
 * Static     -> Stale while revalidate
 * Everything else -> Network only
 */

'use strict';

const VERSION = '2.0.5';

const CACHE_PREFIX = 'afcon360-static-';
const CACHE_NAME = `${CACHE_PREFIX}v${VERSION}`;

const OFFLINE_URL = '/static/offline.html';

const PRECACHE_ASSETS = [
    '/static/css/global/theme-variables.css',
    '/static/css/global/dark-mode.css',
    '/static/css/global/style.css',

    '/static/css/modules/transport/driver-dashboard.css',

    '/static/js/modules/transport/driver-dashboard.js',
    '/static/js/modules/transport/driver_alerts.js',
    '/static/js/modules/transport/driver_offer_poll.js',

    '/static/icons/icon-192.png',
    '/static/icons/icon-512.png',

    '/static/transport/manifest.json'
];

const STATIC_ASSET_PATTERN =
    /\.(css|js|woff2?|ttf|otf|eot|png|jpe?g|svg|webp|ico)$/i;

const SENSITIVE_PATHS = [
    '/static/uploads/',
    '/static/media/',
    '/static/kyc/',
    '/static/documents/',
    '/static/avatars/'
];

function isApiRequest(pathname) {
    const path = pathname.toLowerCase();

    return (
        path === '/api' ||
        path.startsWith('/api/') ||
        path === '/transport/api' ||
        path.startsWith('/transport/api/')
    );
}

function isPublicStaticAsset(url) {
    if (url.origin !== self.location.origin) {
        return false;
    }

    const path = url.pathname.toLowerCase();

    if (!path.startsWith('/static/')) {
        return false;
    }

    if (!STATIC_ASSET_PATTERN.test(path)) {
        return false;
    }

    if (SENSITIVE_PATHS.some(prefix =>
        path.startsWith(prefix)
    )) {
        return false;
    }

    return true;
}

function isSafeCacheableResponse(response) {
    if (!response || !response.ok) return false;

    if (response.type !== 'basic') return false;

    if (response.redirected) return false;

    const contentType =
        response.headers.get('content-type') || '';

    if (contentType.includes('text/html')) return false;

    const cacheControl =
        response.headers.get('cache-control') || '';

    if (/\b(no-store|private)\b/i.test(cacheControl)) {
        return false;
    }

    return true;
}

// The sole HTML cache exception is this public, static, non-personalized page.
// Authenticated dashboard HTML and all other HTML remain network-only.
function isSafeOfflineResponse(response) {
    if (!response || !response.ok) return false;
    if (response.type !== 'basic' || response.redirected) return false;

    const contentType =
        response.headers.get('content-type') || '';
    if (!/text\/html/i.test(contentType)) return false;

    const cacheControl =
        response.headers.get('cache-control') || '';
    if (/\b(no-store|private)\b/i.test(cacheControl)) return false;

    return true;
}

// ======================================================
// INSTALL
// ======================================================

self.addEventListener('install', event => {
    event.waitUntil((async () => {
        const cache = await caches.open(CACHE_NAME);

        // Offline page is mandatory, but we don't want to abort the SW installation
        // if the server temporarily fails to deliver it.
        try {
            const offlineResponse = await fetch(OFFLINE_URL, {
                cache: 'no-store',
                credentials: 'same-origin'
            });

            if (!isSafeOfflineResponse(offlineResponse)) {
                throw new Error('Offline page unavailable or unsafe.');
            }

            await cache.put(OFFLINE_URL, offlineResponse);
        } catch (err) {
            console.error('[SW] CRITICAL: Failed to cache offline page.', err);
            // Continue installation so PWA features still work
        }

        // Other static assets are best-effort.
        await Promise.allSettled(
            PRECACHE_ASSETS.map(async asset => {
                const url = new URL(
                    asset,
                    self.location.origin
                );

                if (!isPublicStaticAsset(url)) {
                    throw new Error(
                        `Rejected asset: ${asset}`
                    );
                }

                const response = await fetch(asset, {
                    cache: 'no-store',
                    credentials: 'same-origin'
                });

                if (!isSafeCacheableResponse(response)) {
                    throw new Error(
                        `Unsafe precache response: ${asset}`
                    );
                }

                await cache.put(
                    asset,
                    response
                );
            })
        );

        await self.skipWaiting();
    })());
});

// ======================================================
// ACTIVATE
// ======================================================

self.addEventListener('activate', event => {
    event.waitUntil((async () => {
        const cacheNames = await caches.keys();

        await Promise.all(
            cacheNames.map(name => {
                if (
                    name.startsWith(CACHE_PREFIX) &&
                    name !== CACHE_NAME
                ) {
                    return caches.delete(name);
                }

                return Promise.resolve();
            })
        );

        await self.clients.claim();
    })());
});

// ======================================================
// FETCH
// ======================================================

self.addEventListener('fetch', event => {
    const request = event.request;

    // Never intercept mutations.
    if (request.method !== 'GET') return;

    const url = new URL(request.url);

    // Same-origin HTTP/S only.
    if (url.origin !== self.location.origin) return;

    if (
        url.protocol !== 'https:' &&
        url.protocol !== 'http:'
    ) {
        return;
    }

    // RULE A: ALL APIs ARE NETWORK ONLY.
    if (isApiRequest(url.pathname)) return;

    // RULE B: HTML IS NEVER CACHED.
    const accept = request.headers.get('accept') || '';

    if (
        request.mode === 'navigate' ||
        accept.includes('text/html')
    ) {
        event.respondWith((async () => {
            try {
                return await fetch(request);
            } catch (error) {
                const offline = await caches.match(OFFLINE_URL);

                if (offline) return offline;

                return new Response(
                    'AFCON360 Transport is offline. Please reconnect.',
                    {
                        status: 503,
                        headers: {
                            'Content-Type':
                                'text/plain; charset=utf-8',
                            'Cache-Control': 'no-store'
                        }
                    }
                );
            }
        })());

        return;
    }

    // RULE C: APPROVED PUBLIC STATIC ASSETS.
    if (isPublicStaticAsset(url)) {
        event.respondWith((async () => {
            const cache = await caches.open(CACHE_NAME);
            const cached = await cache.match(request);

            const networkPromise = (async () => {
                try {
                    const response = await fetch(request);

                    if (isSafeCacheableResponse(response)) {
                        await cache.put(
                            request,
                            response.clone()
                        );
                    }

                    return response;
                } catch (error) {
                    if (cached) return cached;

                    return new Response(
                        'Static resource unavailable offline.',
                        {
                            status: 503,
                            headers: {
                                'Content-Type':
                                    'text/plain; charset=utf-8',
                                'Cache-Control': 'no-store'
                            }
                        }
                    );
                }
            })();

            if (cached) {
                event.waitUntil(
                    networkPromise.then(() => undefined)
                );

                return cached;
            }

            return networkPromise;
        })());

        return;
    }

    // RULE D: EVERYTHING ELSE IS NETWORK ONLY.
    event.respondWith(fetch(request));
});