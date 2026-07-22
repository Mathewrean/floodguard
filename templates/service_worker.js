const CACHE = 'floodguard-v1';
const API_CACHE = 'floodguard-api-v1';

const PRECACHE = [
    '/',
    '/gis/',
    '/safe-route/',
    '/about/',
    '/impact/',
    '/reports/submit/',
    '/static/css/style.css',
    '/static/js/location.js',
    '/static/js/main.js',
    '/static/js/alerts.js',
    '/static/js/offline.js',
    '/static/js/offline_store.js',
];

const API_ROUTES = [
    '/api/v1/zones/',
    '/api/v1/stats/',
    '/api/v1/impact/',
    '/api/v1/milestones/',
    '/health/',
];

self.addEventListener('install', e => {
    e.waitUntil(
        caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', e => {
    e.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE && k !== API_CACHE).map(k => caches.delete(k))
        ).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', e => {
    const url = new URL(e.request.url);
    if (API_ROUTES.some(r => url.pathname.startsWith(r))) {
        e.respondWith(
            caches.open(API_CACHE).then(cache =>
                cache.match(e.request).then(cached => {
                    const network = fetch(e.request).then(res => {
                        if (res.ok) cache.put(e.request, res.clone());
                        return res;
                    }).catch(() => cached);
                    return cached || network;
                })
            )
        );
        return;
    }
    if (e.request.mode === 'navigate') {
        e.respondWith(
            fetch(e.request).catch(() =>
                caches.match(e.request).then(c => c || caches.match('/'))
            )
        );
        return;
    }
    e.respondWith(
        caches.match(e.request).then(c => c || fetch(e.request))
    );
});

self.addEventListener('push', e => {
    const data = e.data ? e.data.json() : {};
    e.waitUntil(
        self.registration.showNotification(data.title || 'FloodGuard Alert', {
            body: data.body || 'New flood alert in your area',
            icon: '/static/icons/icon-192.png',
            badge: '/static/icons/icon-192.png',
            vibrate: [200, 100, 200],
            data: { url: data.url || '/gis/' },
            actions: [{ action: 'view', title: 'View Map' }, { action: 'dismiss', title: 'Dismiss' }],
        })
    );
});

self.addEventListener('notificationclick', e => {
    e.notification.close();
    if (e.action === 'view') {
        e.waitUntil(clients.openWindow(e.notification.data.url || '/gis/'));
    }
});