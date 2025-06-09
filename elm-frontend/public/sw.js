self.addEventListener('push', function (event) {
    console.log('[Service Worker] Push Received.');
    let data = {};
    try {
      data = event.data ? event.data.json() : {};
    } catch (err) {
      console.error('[Service Worker] Failed to parse push data as JSON', err);
    }
  
    const title = data.title || "📢 New Notification";
    const body = data.body || "You have a new message.";
    const icon = 'icon.jpeg';
    const url = data.url || '/'; // Fallback URL
  
    const options = {
      body: body,
      icon: icon,
      badge: icon,
      data: {
        url: url
      }
    };
  
    event.waitUntil(
      self.registration.showNotification(title, options)
    );
  });
  
  self.addEventListener('notificationclick', function (event) {
    event.notification.close();
  
    const targetUrl = event.notification.data.url;
  
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
  