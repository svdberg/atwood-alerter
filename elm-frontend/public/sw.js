const SITE_ICON = '/icon.png';

function isHttps(value) {
  return typeof value === 'string' && value.startsWith('https://');
}

function buildNotification(data) {
  data = data || {};
  const options = {
    body: data.body || '',
    icon: isHttps(data.image_url) ? data.image_url : SITE_ICON,
    badge: SITE_ICON,
    actions: [{ action: 'open', title: 'Open release' }],
    data: { url: data.url || '/' }
  };
  if (isHttps(data.image_url)) {
    options.image = data.image_url;
  }
  if (data.url) {
    options.tag = data.url;
  }
  return { title: data.title || 'New Atwood release', options: options };
}

self.addEventListener('push', function (event) {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (err) {
    console.error('[Service Worker] Failed to parse push data as JSON', err);
  }

  const n = buildNotification(data);
  event.waitUntil(self.registration.showNotification(n.title, n.options));
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();

  const targetUrl = (event.notification.data && event.notification.data.url) || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
      for (let client of clientList) {
        if (client.url === targetUrl && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});
