// Notification management for PettyCash NYSA PWA
// Supports both Android and iOS

class NotificationManager {
  constructor() {
    this.permission = Notification.permission;
    this.isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
    this.isAndroid = /Android/.test(navigator.userAgent);
    this.checkInterval = null;
  }

  async init() {
    console.log(`Initializing notifications for ${this.isIOS ? 'iOS' : this.isAndroid ? 'Android' : 'Desktop'}`);
    
    // Register service worker (Android & Desktop)
    if ('serviceWorker' in navigator && !this.isIOS) {
      try {
        await navigator.serviceWorker.register('/static/service-worker.js');
        console.log('Service Worker registered');
      } catch (error) {
        console.error('Service Worker registration failed:', error);
      }
    }
    
    // Request notification permission
    await this.requestPermission();
    
    // Start periodic check for new notifications (especially for iOS)
    this.startPeriodicCheck();
    
    // For iOS, set up periodic background sync
    if (this.isIOS && 'serviceWorker' in navigator) {
      try {
        const registration = await navigator.serviceWorker.ready;
        if ('periodicSync' in registration) {
          await registration.periodicSync.register('check-approvals', {
            minInterval: 24 * 60 * 60 * 1000 // 24 hours
          });
        }
      } catch (error) {
        console.warn('Periodic sync not supported:', error);
      }
    }
  }

  async requestPermission() {
    if (!('Notification' in window)) {
      console.log('Notifications not supported on this browser');
      return false;
    }

    if (Notification.permission === 'granted') {
      this.permission = 'granted';
      return true;
    }

    if (Notification.permission !== 'denied') {
      try {
        const permission = await Notification.requestPermission();
        this.permission = permission;
        if (permission === 'granted') {
          console.log('Notification permission granted');
        }
        return permission === 'granted';
      } catch (error) {
        console.error('Permission request failed:', error);
        return false;
      }
    }

    return false;
  }

  async sendLocalNotification(title, options = {}) {
    if (this.permission !== 'granted') {
      console.log('Notification permission not granted');
      return false;
    }

    try {
      // For iOS and browsers without service worker
      if (this.isIOS || !('serviceWorker' in navigator)) {
        new Notification(title, {
          icon: '/static/images/logo.png',
          badge: '/static/images/logo.png',
          tag: 'pettycash-notification',
          requireInteraction: true,
          ...options
        });
        return true;
      }

      // For Android and Desktop with Service Worker
      if ('serviceWorker' in navigator) {
        const registration = await navigator.serviceWorker.ready;
        await registration.showNotification(title, {
          icon: '/static/images/logo.png',
          badge: '/static/images/logo.png',
          tag: 'pettycash-notification',
          requireInteraction: true,
          ...options
        });
        return true;
      }
    } catch (error) {
      console.error('Failed to show notification:', error);
    }

    return false;
  }

  startPeriodicCheck() {
    // Check every 5 minutes for pending approvals
    this.checkInterval = setInterval(async () => {
      if (this.permission !== 'granted') return;

      try {
        const response = await fetch('/api/check-notifications');
        const data = await response.json();
        
        if (data.has_pending) {
          await this.sendLocalNotification('PettyCash NYSA', {
            body: `${data.pending_count} expense(s) awaiting approval`,
            badge: '/static/images/logo.png'
          });
        }
      } catch (error) {
        console.error('Failed to check notifications:', error);
      }
    }, 5 * 60 * 1000); // 5 minutes
  }

  stopPeriodicCheck() {
    if (this.checkInterval) {
      clearInterval(this.checkInterval);
      this.checkInterval = null;
    }
  }

  getPermissionStatus() {
    return this.permission;
  }

  getPlatformInfo() {
    return {
      isIOS: this.isIOS,
      isAndroid: this.isAndroid,
      platform: this.isIOS ? 'iOS' : this.isAndroid ? 'Android' : 'Desktop',
      permission: this.permission
    };
  }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', async () => {
  window.notificationManager = new NotificationManager();
  await window.notificationManager.init();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
  if (window.notificationManager) {
    window.notificationManager.stopPeriodicCheck();
  }
});
