const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const TEMPLATE = fs.readFileSync(path.join(__dirname, "../../templates/pwa/sw.js"), "utf8");
const ORIGIN = "https://app.test";
const SHELL = ["/hors-ligne", "/static/css/app.css", "/static/js/offline.js"];

class FakeResponse {
  constructor(body, { status = 200, redirected = false, url = ORIGIN + "/" } = {}) {
    Object.assign(this, { body, status, redirected, url, ok: status >= 200 && status < 300 });
  }
  clone() {
    return new FakeResponse(this.body, this);
  }
}

function build(version = "v1") {
  const store = new Map(); // nom de cache -> Map(url -> réponse)
  const listeners = {};
  const fetched = [];
  let network = (request) => Promise.resolve(new FakeResponse("réseau:" + new URL(request.url || request).pathname));
  const key = (request) => (typeof request === "string" ? new URL(request, ORIGIN).href : request.url);
  const cacheApi = (name) => ({
    put: async (request, response) => store.get(name).set(key(request), response),
    addAll: async (urls) => urls.forEach((u) => store.get(name).set(key(u), new FakeResponse("précache:" + u))),
    keys: async () => [...store.get(name).keys()].map((url) => ({ url })),
  });
  const caches = {
    open: async (name) => {
      if (!store.has(name)) store.set(name, new Map());
      return cacheApi(name);
    },
    match: async (request) => {
      for (const entries of store.values()) {
        if (entries.has(key(request))) return entries.get(key(request));
      }
      return undefined;
    },
    keys: async () => [...store.keys()],
    delete: async (name) => store.delete(name),
  };
  const posted = [];
  const self = {
    location: { origin: ORIGIN },
    addEventListener: (type, handler) => (listeners[type] = handler),
    skipWaiting: () => Promise.resolve(),
    clients: {
      claim: () => Promise.resolve(),
      matchAll: async () => [{ postMessage: (message) => posted.push(message) }],
    },
  };
  const source = TEMPLATE.replace("{{ version }}", version).replace("{{ shell_urls|safe }}", JSON.stringify(SHELL));
  vm.runInNewContext(source, {
    self, caches, URL, Response: FakeResponse,
    fetch: (request) => { fetched.push(request.url || request); return network(request); },
  });
  const waitFor = async (event) => {
    let promise;
    event.waitUntil = (p) => (promise = p);
    return () => promise;
  };
  return {
    store, listeners, fetched, posted,
    setNetwork: (fn) => (network = fn),
    async lifecycle(type, extra = {}) {
      let promise;
      listeners[type]({ waitUntil: (p) => (promise = p), ...extra });
      await promise;
    },
    async request(path, { method = "GET", mode = "navigate", origin = ORIGIN } = {}) {
      let responded;
      let handled = false;
      const event = { request: { method, mode, url: origin + path }, respondWith: (p) => { handled = true; responded = p; } };
      listeners.fetch(event);
      return handled ? { handled, response: await responded } : { handled };
    },
    waitFor,
  };
}

const UUID = "0b9f0a43-6a6c-4e9a-9f7d-3b2a5a8d1c11";

test("l'installation précache l'enveloppe et prend la main sans attendre", async () => {
  const sw = build();
  await sw.lifecycle("install");
  assert.deepEqual([...sw.store.keys()], ["cookup-shell-v1"]);
  assert.equal(sw.store.get("cookup-shell-v1").size, SHELL.length);
});

test("l'activation supprime les anciennes versions mais garde les pages de données", async () => {
  const sw = build("v2");
  sw.store.set("cookup-shell-v1", new Map());
  sw.store.set("cookup-pages", new Map([[ORIGIN + "/courses/" + UUID + "/", new FakeResponse("page")]]));
  sw.store.set("autre-site", new Map());
  await sw.lifecycle("install");
  await sw.lifecycle("activate");
  assert.deepEqual([...sw.store.keys()].sort(), ["autre-site", "cookup-pages", "cookup-shell-v2"]);
});

test("les fichiers statiques sont servis du cache d'abord", async () => {
  const sw = build();
  await sw.lifecycle("install");
  const cached = await sw.request("/static/css/app.css", { mode: "no-cors" });
  assert.equal(cached.response.body, "précache:/static/css/app.css");
  assert.equal(sw.fetched.filter((u) => u.endsWith("app.css")).length, 0);
  const missing = await sw.request("/static/js/autre.js", { mode: "no-cors" });
  assert.equal(missing.response.body, "réseau:/static/js/autre.js");
});

test("une page de données est servie par le réseau et gardée en cache", async () => {
  const sw = build();
  const path = "/courses/" + UUID + "/";
  const result = await sw.request(path);
  assert.equal(result.response.body, "réseau:" + path);
  await new Promise((r) => setImmediate(r));
  assert.ok(sw.store.get("cookup-pages").has(ORIGIN + path));
});

test("sans réseau, la page de données vient du cache", async () => {
  const sw = build();
  const path = "/menus/" + UUID + "/";
  await sw.request(path);
  await new Promise((r) => setImmediate(r));
  sw.setNetwork(() => Promise.reject(new TypeError("hors ligne")));
  const result = await sw.request(path);
  assert.equal(result.response.body, "réseau:" + path);
});

test("sans réseau et sans cache, on affiche la page hors ligne", async () => {
  const sw = build();
  await sw.lifecycle("install");
  sw.setNetwork(() => Promise.reject(new TypeError("hors ligne")));
  const data = await sw.request("/recettes/" + UUID + "/cuisine");
  const other = await sw.request("/menus/");
  assert.equal(data.response.body, "précache:/hors-ligne");
  assert.equal(other.response.body, "précache:/hors-ligne");
});

test("une réponse qui renvoie vers la connexion n'est jamais mise en cache", async () => {
  const sw = build();
  sw.setNetwork(() => Promise.resolve(new FakeResponse("login", { redirected: true, url: ORIGIN + "/connexion?next=/" })));
  await sw.request("/courses/" + UUID + "/");
  await new Promise((r) => setImmediate(r));
  assert.ok(!sw.store.has("cookup-pages") || sw.store.get("cookup-pages").size === 0);
});

test("les erreurs serveur ne sont pas mises en cache", async () => {
  const sw = build();
  sw.setNetwork(() => Promise.resolve(new FakeResponse("boom", { status: 500 })));
  await sw.request("/courses/" + UUID + "/");
  await new Promise((r) => setImmediate(r));
  assert.ok(!sw.store.has("cookup-pages") || sw.store.get("cookup-pages").size === 0);
});

test("jamais d'interception pour les POST, la connexion, le compte, l'admin ni les autres origines", async () => {
  const sw = build();
  assert.equal((await sw.request("/courses/" + UUID + "/synchroniser", { method: "POST" })).handled, false);
  for (const path of ["/connexion", "/deconnexion", "/compte/securite", "/internal/cron/daily", "/invitation/abc", "/admin/login/"]) {
    assert.equal((await sw.request(path)).handled, false, path);
  }
  assert.equal((await sw.request("/courses/" + UUID + "/", { origin: "https://evil.example" })).handled, false);
});

test("les requêtes de données non-navigation (fetch, API) ne sont pas interceptées", async () => {
  const sw = build();
  assert.equal((await sw.request("/courses/" + UUID + "/", { mode: "cors" })).handled, false);
});

test("seules les pages d'un menu, d'une liste ou d'une recette sont traitées comme des données", async () => {
  const sw = build();
  sw.setNetwork(() => Promise.reject(new TypeError("hors ligne")));
  await sw.lifecycle("install");
  for (const path of ["/courses/rayons", "/menus/nouveau", "/foyer/", "/recettes/"]) {
    const result = await sw.request(path);
    assert.equal(result.response.body, "précache:/hors-ligne", path); // repli générique, pas du cache de données
  }
});

test("le message « clear » efface les pages mises en cache (déconnexion)", async () => {
  const sw = build();
  await sw.request("/courses/" + UUID + "/");
  await new Promise((r) => setImmediate(r));
  assert.ok(sw.store.has("cookup-pages"));
  await sw.lifecycle("message", { data: { type: "clear" } });
  assert.ok(!sw.store.has("cookup-pages"));
});

test("l'événement sync réveille les pages ouvertes pour qu'elles synchronisent", async () => {
  const sw = build();
  await sw.lifecycle("sync", { tag: "cookup-sync" });
  assert.equal(JSON.stringify(sw.posted), '[{"type":"flush"}]'); // objets d'un autre contexte vm
  await sw.lifecycle("sync", { tag: "autre" });
  assert.equal(sw.posted.length, 1);
});
