// sw.js - Service Worker aggiornato per le notifiche push

self.addEventListener('install', (event) => {
  console.log('Service Worker: Installazione...');
});

self.addEventListener('activate', (event) => {
  console.log('Service Worker: Attivazione...');
});

self.addEventListener('fetch', (event) => {
  // Per ora, carica tutto dalla rete.
  event.respondWith(fetch(event.request));
});

// --- NUOVO: Ascolta per i messaggi push ---
self.addEventListener('push', (event) => {
  console.log('Service Worker: Ricevuto evento push.');
  
  let data = { title: 'Nuova Notifica', body: 'Qualcosa è successo!' };
  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      console.error('Errore nel parsing del payload push:', e);
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body,
    icon: '/static/icons/icon-192x192.png', // Icona della notifica
    badge: '/static/icons/icon-192x192.png' // Icona per la barra di stato Android
  };

  // Mostra la notifica
  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});