/* Service worker de « Menu du jour » : enveloppe de l'application en cache d'abord, pages de
   données (courses, menus, recettes ouvertes) réseau d'abord avec repli sur le cache.
   Jamais de cache pour les requêtes POST, la connexion, la sécurité du compte ni l'administration. */
const VERSION = "{{ version }}";
const SHELL = "cookup-shell-" + VERSION;
const PAGES = "cookup-pages";
const SHELL_URLS = {{ shell_urls|safe }};
const DATA_PAGE = /^\/(courses\/[0-9a-f-]{36}\/|menus\/[0-9a-f-]{36}\/|recettes\/[0-9a-f-]{36}\/(cuisine)?)$/;
const NEVER = /^\/(connexion|deconnexion|compte|internal|invitation|admin)/;

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL).then((cache) => cache.addAll(SHELL_URLS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) => Promise.all(names.filter((n) => n.startsWith("cookup-shell-") && n !== SHELL).map((n) => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("sync", (event) => {
  // Background Sync (Chrome, Android) : le navigateur nous réveille au retour du réseau.
  if (event.tag === "cookup-sync") {
    event.waitUntil(
      self.clients.matchAll({ type: "window" }).then((clients) => clients.forEach((c) => c.postMessage({ type: "flush" })))
    );
  }
});

self.addEventListener("message", (event) => {
  // Déconnexion : les pages en cache contiennent des données du foyer, on les efface.
  if (event.data && event.data.type === "clear") {
    event.waitUntil(caches.delete(PAGES));
  }
});

function isStatic(url) {
  return url.pathname.startsWith("/static/") || url.pathname === "/manifest.webmanifest";
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  return cached || fetch(request);
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    const loggedOut = response.redirected && NEVER.test(new URL(response.url).pathname);
    if (response.ok && !loggedOut) {
      const copy = response.clone();
      caches.open(PAGES).then((cache) => cache.put(request, copy));
    }
    return response;
  } catch (error) {
    return (await caches.match(request)) || (await caches.match("/hors-ligne")) || Response.error();
  }
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin || NEVER.test(url.pathname)) {
    return;
  }
  if (isStatic(url)) {
    event.respondWith(cacheFirst(request));
  } else if (request.mode === "navigate" && DATA_PAGE.test(url.pathname)) {
    event.respondWith(networkFirst(request));
  } else if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match("/hors-ligne")));
  }
});
