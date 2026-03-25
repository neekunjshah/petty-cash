// Service Worker for PettyCash NYSA PWA
// Supports caching, offline access, and notifications

const CACHE_NAME = 'pettycash-v1';
const PRECACHE_URLS = [
  '/',
  '/static/css/app.css',
  '/static/images/logo.png',
  '/static/manifest.json',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.2/font/bootstrap-icons.css',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Skip non-GET requests and API calls
  if (event.request.method !== 'GET') return;
  if (url.pathname.startsWith('/api/')) return;

  // Static assets & CDN: cache-first
  if (url.pathname.startsWith('/static/') || url.hostname.includes('cdn.jsdelivr.net')) {
    event.respondWith(
      caches.match(event.request).then((cached) =>
        cached || fetch(event.request).then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          return response;
        })
      )
    );
    return;
  }

  // Page navigations: network-first with cache fallback
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }
});

// Periodic background sync for checking approvals (mainly for iOS)
self.addEventListener('periodicsync', (event) => {
  if (event.tag === 'check-approvals') {
    event.waitUntil(checkAndNotifyApprovals());
  }
});

async function checkAndNotifyApprovals() {
  try {
    const response = await fetch('/api/check-notifications');
    const data = await response.json();

    if (data.has_pending) {
      await self.registration.showNotification('PettyCash NYSA', {
        body: `${data.pending_count} expense(s) awaiting approval`,
        icon: '/static/images/logo.png',
        badge: '/static/images/logo.png',
        tag: 'approval-notification',
        requireInteraction: true,
        data: { url: '/dashboard' }
      });
    }
  } catch (error) {
    console.error('Background sync error:', error);
  }
}

self.addEventListener('push', (event) => {
  let notificationData = {
    title: 'PettyCash NYSA',
    body: 'New expense awaiting approval',
    icon: '/static/images/logo.png',
    badge: '/static/images/logo.png',
    tag: 'approval-notification',
    requireInteraction: true
  };

  if (event.data) {
    try {
      notificationData = { ...notificationData, ...event.data.json() };
    } catch (e) {
      notificationData.body = event.data.text();
    }
  }

  event.waitUntil(
    self.registration.showNotification(notificationData.title, {
      body: notificationData.body,
      icon: notificationData.icon,
      badge: notificationData.badge,
      tag: notificationData.tag,
      requireInteraction: notificationData.requireInteraction,
      data: { url: '/dashboard' }
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then((clientList) => {
      for (const client of clientList) {
        if (client.url === '/' && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow('/dashboard');
      }
    })
  );
});

self.addEventListener('notificationclose', (event) => {
  console.log('Notification closed');
});
