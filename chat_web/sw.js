// Service Worker — ProsArtisan IA Expert (PWA)
//
// Objectif : coquille applicative disponible hors-ligne (shell + assets
// statiques), pertinent vu le contexte de connectivité 3G/4G faible décrit
// dans CLAUDE.md. Les réponses de l'API (RAG) ne sont volontairement PAS
// mises en cache ici : une réponse technique périmée servie hors-ligne
// serait pire qu'une absence de réponse.

const CACHE_NAME = 'prosartisan-shell-v1';
const SHELL_ASSETS = [
  '/chat/',
  '/chat/styles.css',
  '/chat/app.js',
  '/chat/manifest.json',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Ne jamais intercepter les appels API : toujours réseau, jamais de cache
  // périmé pour une réponse technique ou un état de quota/session.
  if (url.pathname.startsWith('/api/')) {
    return;
  }

  // Assets statiques du shell : cache d'abord, réseau en repli.
  event.respondWith(
    caches.match(event.request).then((cached) => {
      return (
        cached ||
        fetch(event.request).catch(() => caches.match('/chat/'))
      );
    })
  );
});

// Réception d'une notification Web Push (nécessite des clés VAPID côté
// backend — voir docs/PLAN_AMELIORATION.md, item 3.2, pour l'activation
// complète). Le listener est prêt, même si aucune poussée n'est encore
// déclenchée côté serveur.
self.addEventListener('push', (event) => {
  let payload = { title: 'ProsArtisan IA', body: 'Nouvelle notification.' };
  try {
    if (event.data) payload = event.data.json();
  } catch (_) {
    /* payload texte brut, on garde le message par défaut */
  }

  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: '/admin/assets/images/favicon.ico',
    })
  );
});
