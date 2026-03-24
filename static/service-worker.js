// Service Worker for PettyCash NYSA PWA
// Supports Android and Desktop notifications

self.addEventListener('install', (event) => {
  console.log('Service Worker installing...');
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  console.log('Service Worker activated');
  event.waitUntil(clients.claim());
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
  console.log('Push notification received:', event.data);
  
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
