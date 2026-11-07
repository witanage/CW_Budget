// Service Worker for Personal Finance Manager PWA
importScripts('/static/js/offline_queue.js');   // defines self.OfflineQueue

const CACHE_NAME = 'finance-manager-v1.1.0';
const RUNTIME_CACHE = 'finance-manager-runtime-v1.1.0';
// Per-user reference data (categories, payment methods) so the add-transaction
// form still works offline. Cleared on logout so it never leaks between users.
const API_CACHE = 'finance-manager-api-v1.1.0';
const CACHEABLE_API_PATHS = [
  '/api/categories',
  '/api/payment-methods',
  '/api/settings/upload-mode'
];

// Assets to cache on install
const STATIC_ASSETS = [
  '/',
  '/static/css/base.css',
  '/static/css/loader.css',
  '/static/css/dashboard.css',
  '/static/css/mobile.css',
  '/static/css/vendor/bootstrap.min.css',
  '/static/css/vendor/fontawesome.min.css',
  '/static/js/base.js',
  '/static/js/offline_queue.js',
  '/static/js/dashboard.js',
  '/static/js/mobile.js',
  '/static/js/vendor/bootstrap.bundle.min.js',
  '/static/js/vendor/chart.min.js',
  '/static/manifest.json',
  '/static/favicon.ico'
];

// Install event - cache static assets
self.addEventListener('install', (event) => {
  console.log('[Service Worker] Installing...');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('[Service Worker] Caching static assets');
        return cache.addAll(STATIC_ASSETS.map(url => new Request(url, {credentials: 'same-origin'})));
      })
      .then(() => self.skipWaiting())
      .catch((error) => {
        console.error('[Service Worker] Installation failed:', error);
      })
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  console.log('[Service Worker] Activating...');
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((cacheName) => {
            return cacheName !== CACHE_NAME && cacheName !== RUNTIME_CACHE && cacheName !== API_CACHE;
          })
          .map((cacheName) => {
            console.log('[Service Worker] Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch event - network first, then cache fallback
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== 'GET') {
    return;
  }

  // Skip chrome extensions and non-http(s) requests
  if (!url.protocol.startsWith('http')) {
    return;
  }

  // Logging out: drop cached per-user API data and pages
  if (url.pathname === '/logout') {
    event.waitUntil(Promise.all([caches.delete(API_CACHE), caches.delete(RUNTIME_CACHE)]));
  }

  // Reference data for the offline add-transaction form: network first, cache fallback
  if (CACHEABLE_API_PATHS.includes(url.pathname)) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Only cache real JSON answers (not a login redirect page)
          const type = response.headers.get('content-type') || '';
          if (response.ok && !response.redirected && type.includes('json')) {
            const copy = response.clone();
            caches.open(API_CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() =>
          caches.open(API_CACHE).then((cache) => cache.match(request)).then((cached) =>
            cached || new Response(
              JSON.stringify({ error: 'You are offline. This action requires an internet connection.' }),
              { headers: { 'Content-Type': 'application/json' }, status: 503 }
            )
          )
        )
    );
    return;
  }

  // API requests - network only with offline message
  if (url.pathname.startsWith('/api/') || 
      url.pathname.includes('/login') || 
      url.pathname.includes('/logout')) {
    event.respondWith(
      fetch(request)
        .catch(() => {
          return new Response(
            JSON.stringify({ error: 'You are offline. This action requires an internet connection.' }),
            {
              headers: { 'Content-Type': 'application/json' },
              status: 503
            }
          );
        })
    );
    return;
  }

  // Static assets - cache first, then network
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request)
        .then((response) => {
          if (response) {
            return response;
          }
          return fetch(request).then((response) => {
            // Cache successful responses
            if (response.status === 200) {
              const responseToCache = response.clone();
              caches.open(CACHE_NAME).then((cache) => {
                cache.put(request, responseToCache);
              });
            }
            return response;
          });
        })
    );
    return;
  }

  // HTML pages - network first, cache fallback
  event.respondWith(
    fetch(request)
      .then((response) => {
        // Clone and cache successful HTML responses
        if (response.status === 200 && response.type === 'basic') {
          const responseToCache = response.clone();
          caches.open(RUNTIME_CACHE).then((cache) => {
            cache.put(request, responseToCache);
          });
        }
        return response;
      })
      .catch(() => {
        // Try to serve from cache
        return caches.match(request)
          .then((response) => {
            if (response) {
              return response;
            }
            // Return offline page if available
            return caches.match('/').then((fallback) => {
              return fallback || new Response(
                '<html><body><h1>Offline</h1><p>You are currently offline. Please check your internet connection.</p></body></html>',
                { headers: { 'Content-Type': 'text/html' } }
              );
            });
          });
      })
  );
});

// Handle messages from clients
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  
  if (event.data && event.data.type === 'FLUSH_OFFLINE_QUEUE') {
    event.waitUntil(self.OfflineQueue.flush().catch(() => {}));
  }

  if (event.data && event.data.type === 'CLEAR_CACHE') {
    event.waitUntil(
      caches.keys().then((cacheNames) => {
        return Promise.all(
          cacheNames.map((cacheName) => caches.delete(cacheName))
        );
      }).then(() => {
        event.ports[0].postMessage({ success: true });
      })
    );
  }
});

// Background sync: replay transactions queued while offline.
// Rejecting makes the browser retry later; we do not retry when the session
// has expired (the page prompts the user to log in again instead).
self.addEventListener('sync', (event) => {
  if (event.tag === self.OfflineQueue.SYNC_TAG) {
    event.waitUntil(
      self.OfflineQueue.flush().then((summary) => {
        if (summary.remaining > 0 && !summary.authRequired) {
          throw new Error('Offline queue not empty yet');
        }
      })
    );
  }
});

// Push notifications support (future enhancement)
self.addEventListener('push', (event) => {
  if (event.data) {
    const data = event.data.json();
    const options = {
      body: data.body,
      icon: '/static/icons/icon-192x192.png',
      badge: '/static/icons/icon-72x72.png',
      vibrate: [200, 100, 200],
      tag: data.tag || 'finance-notification',
      requireInteraction: false
    };
    
    event.waitUntil(
      self.registration.showNotification(data.title, options)
    );
  }
});

// Notification click handler
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    clients.openWindow('/')
  );
});
