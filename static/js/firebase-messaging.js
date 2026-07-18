import { initializeApp } from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js';
import { getMessaging, getToken, onMessage } from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-messaging.js';

let messaging;
let firebaseConfig;
let foregroundListenerRegistered = false;

async function getConfig() {
  if (firebaseConfig) return firebaseConfig;
  const response = await Auth.apiFetch('/api/v1/notifications/config');
  if (!response || !response.success) {
    throw new Error(response?.message || 'Firebase messaging is not configured.');
  }
  firebaseConfig = response.data;
  return firebaseConfig;
}

async function enable() {
  if (!('serviceWorker' in navigator) || !('Notification' in window)) {
    showToast('Push notifications are not supported by this browser.', 'warning');
    return;
  }
  if (Notification.permission === 'denied') {
    showToast('Notifications are blocked. Enable them in your browser settings.', 'warning');
    return;
  }

  try {
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      showToast('Notification permission was not granted.', 'warning');
      return;
    }

    const { config, registration } = await initializeMessaging();
    const token = await getToken(messaging, {
      vapidKey: config.vapidKey,
      serviceWorkerRegistration: registration,
    });
    if (!token) throw new Error('Firebase did not return a device token.');

    const deviceName = `${navigator.platform || 'Browser'} (${navigator.userAgent.slice(0, 60)})`;
    const saved = await Auth.apiFetch('/api/v1/notifications/devices', {
      method: 'POST',
      body: JSON.stringify({ token, platform: 'web', device_name: deviceName }),
    });
    if (!saved || !saved.success) throw new Error(saved?.message || 'Could not register this device.');

    showToast('Push notifications are enabled on this device.', 'success');
  } catch (error) {
    console.error('Unable to enable Firebase notifications:', error);
    showToast(error.message || 'Could not enable notifications.', 'error');
  }
}

async function initializeMessaging() {
  const config = await getConfig();
  const registration = await navigator.serviceWorker.register('/firebase-messaging-sw.js');

  // Ensure the service worker is active/activated to prevent 'no active Service Worker' error
  await new Promise((resolve) => {
    const activeWorker = registration.active || registration.installing || registration.waiting;
    if (activeWorker) {
      if (activeWorker.state === 'activated') {
        resolve();
      } else {
        activeWorker.addEventListener('statechange', function onStateChange(e) {
          if (e.target.state === 'activated' || e.target.state === 'redundant') {
            activeWorker.removeEventListener('statechange', onStateChange);
            resolve();
          }
        });
      }
    } else {
      resolve();
    }
  });

  messaging = messaging || getMessaging(initializeApp(config));

  if (!foregroundListenerRegistered) {
    onMessage(messaging, (payload) => {
      const notification = payload.notification || {};
      const title = notification.title || 'ExpenseTracker notification';
      const body = notification.body || 'You have a new notification.';
      showToast(title, 'success');

      // FCM automatically shows notification payloads in the background.
      // In the foreground, explicitly show a native notification as well.
      if (Notification.permission === 'granted') {
        new Notification(title, { body, icon: '/static/images/avatar.png' });
      }
    });
    foregroundListenerRegistered = true;
  }
  return { config, registration };
}

window.addEventListener('load', async () => {
  if (!('Notification' in window) || Notification.permission !== 'granted') return;

  try {
    const { config, registration } = await initializeMessaging();
    const token = await getToken(messaging, {
      vapidKey: config.vapidKey,
      serviceWorkerRegistration: registration,
    });
    if (!token) return;

    const deviceName = `${navigator.platform || 'Browser'} (${navigator.userAgent.slice(0, 60)})`;
    await Auth.apiFetch('/api/v1/notifications/devices', {
      method: 'POST',
      body: JSON.stringify({ token, platform: 'web', device_name: deviceName }),
    });
  } catch (error) {
    console.warn('Unable to restore Firebase message listener:', error);
  }
});

window.NotificationManager = { enable };
