let messaging;
let firebaseConfig;
let foregroundListenerRegistered = false;

// Dynamic imports cache
let initializeAppFn;
let getMessagingFn;
let getTokenFn;
let onMessageFn;

async function loadFirebaseSDKs() {
  if (initializeAppFn) {
    console.log('[FCM] Firebase SDKs are already loaded.');
    return;
  }
  
  console.log('[FCM] Dynamically importing Firebase SDK modules...');
  // Dynamically import the modules so they are not evaluated before service worker is ready
  const appMod = await import('https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js');
  const messagingMod = await import('https://www.gstatic.com/firebasejs/10.14.1/firebase-messaging.js');
  
  initializeAppFn = appMod.initializeApp;
  getMessagingFn = messagingMod.getMessaging;
  getTokenFn = messagingMod.getToken;
  onMessageFn = messagingMod.onMessage;
  console.log('[FCM] Firebase SDK modules successfully loaded and mapped.');
}

async function getConfig() {
  if (firebaseConfig) {
    console.log('[FCM] Using cached Firebase web config.');
    return firebaseConfig;
  }
  
  console.log('[FCM] Checking if Auth module is available...');
  if (typeof Auth === 'undefined' || !Auth.apiFetch) {
    throw new Error('Auth module is not loaded yet.');
  }
  
  console.log('[FCM] Fetching Firebase web configuration from backend...');
  const response = await Auth.apiFetch('/api/v1/notifications/config');
  if (!response || !response.success) {
    throw new Error(response?.message || 'Firebase messaging is not configured.');
  }
  
  firebaseConfig = response.data;
  console.log('[FCM] Firebase config successfully fetched:', firebaseConfig);
  return firebaseConfig;
}

async function enable() {
  console.log('[FCM] Enable clicked. Verifying browser support...');
  if (!('serviceWorker' in navigator) || !('Notification' in window) || !('PushManager' in window)) {
    window.showToast?.('Push notifications/PushManager are not supported by this browser.', 'warning');
    console.warn('[FCM] Push notifications / PushManager are not supported in this browser.');
    return;
  }
  
  console.log('[FCM] Checking current notification permission status:', Notification.permission);
  if (Notification.permission === 'denied') {
    window.showToast?.('Notifications are blocked. Enable them in your browser settings.', 'warning');
    console.warn('[FCM] Notification permissions are blocked/denied by the user.');
    return;
  }

  try {
    console.log('[FCM] Requesting notification permission from user...');
    const permission = await Notification.requestPermission();
    console.log('[FCM] User response to permission request:', permission);
    if (permission !== 'granted') {
      window.showToast?.('Notification permission was not granted.', 'warning');
      return;
    }

    console.log('[FCM] Initializing messaging pipeline...');
    const { config, registration } = await initializeMessaging();
    
    console.log('[FCM] Requesting device token from Firebase Messaging...');
    const token = await getTokenFn(messaging, {
      vapidKey: config.vapidKey,
      serviceWorkerRegistration: registration,
    });
    if (!token) throw new Error('Firebase did not return a device token.');
    
    console.log('[FCM] Token retrieved successfully. Length:', token.length);

    const deviceName = `${navigator.platform || 'Browser'} (${navigator.userAgent.slice(0, 60)})`;
    console.log('[FCM] Registering device token with backend server. Device name:', deviceName);
    
    const saved = await Auth.apiFetch('/api/v1/notifications/devices', {
      method: 'POST',
      body: JSON.stringify({ token, platform: 'web', device_name: deviceName }),
    });
    
    if (!saved || !saved.success) {
      throw new Error(saved?.message || 'Could not register this device.');
    }

    console.log('[FCM] Device token registered successfully with backend.');
    window.showToast?.('Push notifications are enabled on this device.', 'success');
  } catch (error) {
    console.error('[FCM] Unable to enable Firebase notifications. Error details:');
    console.dir(error);
    if (error.code) {
      console.error(`[FCM] Error Code: ${error.code}`);
    }
    window.showToast?.(error.message || 'Could not enable notifications.', 'error');
  }
}

async function initializeMessaging() {
  console.log('[FCM] Initializing service worker and messaging configuration...');
  const config = await getConfig();

  // Detect Firebase project changes and unregister stale service workers
  const lastProjectId = localStorage.getItem('fcm_project_id');
  console.log(`[FCM] Validating project ID. Stored: "${lastProjectId}", Current config: "${config.projectId}"`);
  if (lastProjectId === null) {
    console.log('[FCM] Initial setup. Storing project ID.');
    localStorage.setItem('fcm_project_id', config.projectId);
  } else if (lastProjectId !== config.projectId) {
    console.log(`[FCM] Firebase project changed from "${lastProjectId}" to "${config.projectId}". Cleaning up stale workers...`);
    try {
      const registrations = await navigator.serviceWorker.getRegistrations();
      for (const reg of registrations) {
        const activeWorker = reg.active || reg.installing || reg.waiting;
        if (activeWorker && activeWorker.scriptURL.endsWith('/firebase-messaging-sw.js')) {
          console.log('[FCM] Unregistering stale Firebase service worker:', activeWorker.scriptURL);
          await reg.unregister();
        }
      }
    } catch (e) {
      console.warn('[FCM] Failed to unregister old service workers:', e);
    }
    localStorage.setItem('fcm_project_id', config.projectId);
    console.log('[FCM] Project ID updated. Reloading page for a clean state...');
    window.location.reload();
    return new Promise(() => { }); // Halt execution and wait for reload
  }

  // Clean up any service workers that are not /firebase-messaging-sw.js
  try {
    const registrations = await navigator.serviceWorker.getRegistrations();
    for (const reg of registrations) {
      const activeWorker = reg.active || reg.installing || reg.waiting;
      if (activeWorker && !activeWorker.scriptURL.endsWith('/firebase-messaging-sw.js')) {
        console.log('[FCM] Cleaning up incorrect/stale service worker path:', activeWorker.scriptURL);
        await reg.unregister();
      }
    }
  } catch (e) {
    console.warn('[FCM] Failed to clean up incorrect service workers:', e);
  }

  console.log('[FCM] Registering service worker: /firebase-messaging-sw.js');
  await navigator.serviceWorker.register('/firebase-messaging-sw.js');
  
  console.log('[FCM] Awaiting service worker ready state...');
  const registration = await navigator.serviceWorker.ready;
  console.log('[FCM] Service worker is active and ready on scope:', registration.scope);

  // Dynamically load Firebase SDKs only after service worker registration is ready
  // This prevents background evaluation of listeners from failing on undefined getRegistration()
  await loadFirebaseSDKs();

  if (!messaging) {
    console.log('[FCM] Initializing Firebase app and getting messaging instance...');
    messaging = getMessagingFn(initializeAppFn(config));
  }

  if (!foregroundListenerRegistered) {
    console.log('[FCM] Registering foreground message handler...');
    onMessageFn(messaging, (payload) => {
      console.log('[FCM] Foreground notification payload received:', payload);
      const notification = payload.notification || {};
      const title = notification.title || 'ExpenseTracker notification';
      const body = notification.body || 'You have a new notification.';
      window.showToast?.(title, 'success');

      if (Notification.permission === 'granted') {
        new Notification(title, { body, icon: '/static/images/avatar.png' });
      }
    });
    foregroundListenerRegistered = true;
  }
  
  console.log('[FCM] Initialization complete.');
  return { config, registration };
}

window.addEventListener('load', () => {
  console.log('[FCM] Window load. Checking API support...');
  if (!('Notification' in window)) {
    console.log('[FCM] Notification API not available.');
    return;
  }
  console.log('[FCM] Permission state:', Notification.permission);
  if (Notification.permission === 'granted') {
    console.log('[FCM] Permission is already granted. Attempting to restore messaging listener...');
    initializeMessaging()
      .then(async ({ config, registration }) => {
        try {
          console.log('[FCM] Requesting token on load to confirm active registration...');
          const token = await getTokenFn(messaging, {
            vapidKey: config.vapidKey,
            serviceWorkerRegistration: registration,
          });
          if (token) {
            console.log('[FCM] Token retrieved on load. Length:', token.length);
            const deviceName = `${navigator.platform || 'Browser'} (${navigator.userAgent.slice(0, 60)})`;
            await Auth.apiFetch('/api/v1/notifications/devices', {
              method: 'POST',
              body: JSON.stringify({ token, platform: 'web', device_name: deviceName }),
            });
            console.log('[FCM] Token registered with backend on page load.');
          } else {
            console.warn('[FCM] No token retrieved on page load.');
          }
        } catch (err) {
          console.warn('[FCM] Failed to retrieve/register token on page load. Error details:');
          console.dir(err);
        }
      })
      .catch((error) => {
        console.warn('[FCM] Unable to restore Firebase message listener. Error details:');
        console.dir(error);
      });
  } else {
    console.log('[FCM] Notifications are not yet enabled or not granted on this device.');
  }
});

window.NotificationManager = { enable };
