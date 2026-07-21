const CACHE_NAME = 'feediverse-v2-fts5';
const STATIC_ASSETS = [
    '/',
    '/static/index.html',
    '/static/style.css',
    '/static/app.js',
    '/static/manifest.json',
    '/static/icon-192.png',
    '/static/icon-512.png',
];

// Install — cache static assets
self.addEventListener('install', e => {
    e.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
    );
    self.skipWaiting();
});

// Activate — clean old caches
self.addEventListener('activate', e => {
    e.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        )
    );
    self.clients.claim();
});

// Fetch — stale-while-revalidate for API, cache-first for static
self.addEventListener('fetch', e => {
    const url = new URL(e.request.url);

    // API requests: network first, fallback to cache
    if (url.pathname.startsWith('/api/')) {
        e.respondWith(
            fetch(e.request)
                .then(res => {
                    const copy = res.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(e.request, copy));
                    return res;
                })
                .catch(() => caches.match(e.request))
        );
        return;
    }

    // Static assets: cache first, then network
    e.respondWith(
        caches.match(e.request).then(cached =>
            cached || fetch(e.request).then(res => {
                const copy = res.clone();
                caches.open(CACHE_NAME).then(cache => cache.put(e.request, copy));
                return res;
            })
        )
    );
});