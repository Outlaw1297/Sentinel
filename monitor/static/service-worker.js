const SHELL_CACHE = "sentinel-shell-v8";
const NETWORK_FIRST_STATIC = new Set([
  "/static/settings.js",
  "/static/app.js",
  "/static/restore-shared.js",
]);
const NOTIFICATION_ICON = "/static/icons/notification-icon.png?v=1";
const NOTIFICATION_BADGE = "/static/icons/notification-badge.png?v=1";
const SHELL_ASSETS = [
  "/",
  "/favicon.ico",
  "/favicon.png?v=7",
  "/static/styles.css?v=73",
  "/static/app.js?v=75",
  "/static/settings.js?v=60",
  "/static/restore-shared.js?v=4",
  "/static/notifications.js?v=8",
  "/static/sentinel-icons.js?v=1",
  "/static/manifest.webmanifest",
  "/static/icons/sentinel-logo.png?v=5",
  "/static/icons/icon-192.png?v=7",
  "/static/icons/icon-512.png?v=7",
  "/static/icons/apple-touch-icon.png?v=7",
  "/static/icons/notification-icon.png?v=1",
  "/static/icons/notification-badge.png?v=1",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_ASSETS)).catch(() => undefined),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== SHELL_CACHE).map((key) => caches.delete(key))),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith("/api/")) {
    return;
  }
  if (event.request.method !== "GET") {
    return;
  }

  if (NETWORK_FIRST_STATIC.has(url.pathname) || url.pathname === "/") {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          if (response.ok && url.origin === self.location.origin) {
            const copy = response.clone();
            caches.open(SHELL_CACHE).then((cache) => cache.put(event.request, copy));
          }
          return response;
        })
        .catch(() => caches.match(event.request)),
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      const network = fetch(event.request)
        .then((response) => {
          if (response.ok && url.origin === self.location.origin && !url.pathname.startsWith("/api/")) {
            const copy = response.clone();
            caches.open(SHELL_CACHE).then((cache) => cache.put(event.request, copy));
          }
          return response;
        })
        .catch(() => cached);
      return cached || network;
    }),
  );
});

function notificationOptions(payload = {}) {
  return {
    body: payload.body || "",
    tag: payload.tag || "sentinel",
    // Large color icon for expanded/popup notifications.
    icon: payload.icon || NOTIFICATION_ICON,
    // Status-bar / condensed tray icon: Android expects a white alpha mask.
    badge: payload.badge || NOTIFICATION_BADGE,
    data: {
      url: payload.url || "/",
    },
    renotify: true,
  };
}

self.addEventListener("push", (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (_error) {
    payload = { title: "Sentinel", body: event.data ? event.data.text() : "" };
  }

  const title = payload.title || "Sentinel";
  event.waitUntil(self.registration.showNotification(title, notificationOptions(payload)));
});

self.addEventListener("message", (event) => {
  const data = event.data || {};
  if (data.type !== "local-notification") {
    return;
  }
  event.waitUntil(
    self.registration.showNotification(
      data.title || "Sentinel",
      notificationOptions({
        body: data.body || "",
        tag: data.tag || "sentinel-local",
        url: data.url || "/",
      }),
    ),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = event.notification.data?.url || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ("focus" in client) {
          client.navigate(target);
          return client.focus();
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(target);
      }
      return undefined;
    }),
  );
});
