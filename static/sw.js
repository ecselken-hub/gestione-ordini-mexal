// sw.js - Service Worker minimale per l'installabilità

self.addEventListener('install', (event) => {
  console.log('Service Worker: Installazione...');
  // self.skipWaiting(); // Forza l'attivazione immediata (opzionale)
});

self.addEventListener('activate', (event) => {
  console.log('Service Worker: Attivazione...');
});

self.addEventListener('fetch', (event) => {
  // Per ora, carica tutto dalla rete.
  // In futuro, qui si può aggiungere la logica di caching.
  event.respondWith(fetch(event.request));
});