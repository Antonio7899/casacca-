const CACHE_NAME = 'stewardapp-cache-v2';
const urlsToCache = [
  '/',
  '/dashboard',
  '/events',
  '/finanze',
  '/stewards',
  '/notifiche_eventi',
  '/static/favicon.ico',
  '/static/manifest.json',
  '/static/logo192.png',
  '/static/logo512.png',
  '/static/service-worker.js',
  '/static/index.css'
];
self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(function(cache) {
        return cache.addAll(urlsToCache);
      })
  );
});
self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(cacheNames) {
      return Promise.all(
        cacheNames.filter(function(name) { return name !== CACHE_NAME; })
          .map(function(name) { return caches.delete(name); })
      );
    })
  );
});
self.addEventListener('fetch', function(event) {
  event.respondWith(
    caches.match(event.request)
      .then(function(response) {
        return response || fetch(event.request).catch(() => offlineResponse(event.request));
      })
  );
});
self.addEventListener('push', function(event) {
  const data = event.data ? event.data.json() : { title: 'Notifica', body: 'Hai una nuova notifica!' };
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/static/favicon.ico',
      badge: '/static/favicon.ico'
    })
  );
});
function offlineResponse(request) {
  if (request.destination === 'document' || request.mode === 'navigate') {
    return new Response('<!DOCTYPE html><html><head><title>Offline</title><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{font-family:sans-serif;text-align:center;padding:40px;}h1{color:#757de8;}button{background:#757de8;color:#fff;padding:10px 20px;border:none;border-radius:8px;font-size:1.1em;}</style></head><body><h1>Sei offline</h1><p>Non hai connessione a Internet.<br>Puoi comunque consultare le pagine già visitate.<br><button onclick="location.reload()">Riprova</button></p></body></html>', { headers: { 'Content-Type': 'text/html' } });
  }
  return Response.error();
} 