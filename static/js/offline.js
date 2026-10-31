/* Hors ligne : service worker, file d'attente IndexedDB, synchronisation et déconnexion.
   La logique pure est dans outbox.js ; ici, tout ce qui touche au navigateur. */
(function () {
  "use strict";

  var Outbox = self.CookupOutbox;
  var DB_NAME = "cookup";
  var STORE = "outbox";
  var LOGOUT_FLAG = "cookup-logout-pending";
  var PAGES_CACHE = "cookup-pages";
  var attempt = 0;
  var flushing = false;
  var retryTimer = null;

  /* ---------- IndexedDB ---------- */
  function openDb() {
    return new Promise(function (resolve, reject) {
      var request = indexedDB.open(DB_NAME, 1);
      request.onupgradeneeded = function () {
        request.result.createObjectStore(STORE, { keyPath: "id" });
      };
      request.onsuccess = function () {
        resolve(request.result);
      };
      request.onerror = function () {
        reject(request.error);
      };
    });
  }

  function withStore(mode, work) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var transaction = db.transaction(STORE, mode);
        var result = work(transaction.objectStore(STORE));
        transaction.oncomplete = function () {
          db.close();
          resolve(result && result.result);
        };
        transaction.onerror = function () {
          reject(transaction.error);
        };
      });
    });
  }

  var queue = {
    all: function () {
      return withStore("readonly", function (store) {
        return store.getAll();
      }).then(function (rows) {
        return rows || [];
      });
    },
    put: function (operation) {
      return withStore("readwrite", function (store) {
        return store.put(operation);
      });
    },
    remove: function (ids) {
      return withStore("readwrite", function (store) {
        ids.forEach(function (id) {
          store.delete(id);
        });
      });
    },
    clear: function () {
      return withStore("readwrite", function (store) {
        return store.clear();
      });
    },
  };

  /* ---------- Aides ---------- */
  function csrfToken(root) {
    var names = [(root && root.dataset.csrfCookie) || "", "__Host-csrftoken", "csrftoken"];
    for (var i = 0; i < names.length; i++) {
      var match = names[i] && document.cookie.match("(?:^|; )" + names[i] + "=([^;]*)");
      if (match) {
        return decodeURIComponent(match[1]);
      }
    }
    return "";
  }

  function status(message, withLogin) {
    var box = document.getElementById("sync-status");
    if (!box) {
      return;
    }
    box.textContent = message;
    box.hidden = !message;
    if (message && withLogin) {
      var link = document.createElement("a");
      link.href = "/connexion?next=" + encodeURIComponent(location.pathname);
      link.textContent = " Se reconnecter";
      box.appendChild(link);
    }
  }

  function describePending(count) {
    return count === 1 ? "1 modification en attente de synchronisation." : count + " modifications en attente de synchronisation.";
  }

  /* ---------- Affichage de la liste ---------- */
  function paintChecked(li, checked) {
    li.classList.toggle("done", checked);
    li.dataset.checked = checked ? "1" : "0";
    var button = li.querySelector('form[data-action="toggle"] button');
    if (button) {
      button.textContent = checked ? "☑" : "☐";
      button.setAttribute("aria-pressed", checked ? "true" : "false");
    }
  }

  function applyPending(operations) {
    var state = Outbox.pendingState(operations);
    document.querySelectorAll("[data-item]").forEach(function (li) {
      var pending = state[li.dataset.item];
      if (!pending) {
        return;
      }
      if (pending.removed) {
        li.hidden = true;
      } else {
        paintChecked(li, pending.checked);
      }
    });
  }

  function reconcile(snapshot) {
    var known = {};
    snapshot.items.forEach(function (item) {
      known[item.id] = item;
    });
    var shown = 0;
    document.querySelectorAll("[data-item]").forEach(function (li) {
      var item = known[li.dataset.item];
      if (item) {
        shown += 1;
        paintChecked(li, item.checked);
      } else {
        li.hidden = true;
      }
    });
    if (shown !== snapshot.items.length) {
      status("La liste a changé sur un autre appareil : actualisez la page pour la voir en entier.");
    }
  }

  /* ---------- Synchronisation ---------- */
  function flush() {
    var root = document.querySelector("[data-shopping]");
    if (!root || flushing || !navigator.onLine) {
      return Promise.resolve();
    }
    flushing = true;
    return queue
      .all()
      .then(function (stored) {
        var operations = Outbox.collapse(stored);
        if (!stored.length) {
          return null;
        }
        return send(root, operations, stored);
      })
      .catch(function () {
        scheduleRetry();
      })
      .then(function () {
        flushing = false;
      });
  }

  function send(root, operations, stored) {
    return fetch(root.dataset.syncUrl, {
      method: "POST",
      credentials: "same-origin",
      redirect: "manual",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken(root) },
      body: JSON.stringify({ operations: operations }),
    }).then(function (response) {
      var code = response.type === "opaqueredirect" ? 302 : response.status;
      var verdict = Outbox.classify(code);
      if (verdict === "ok") {
        return response.json().then(function (body) {
          // Tout ce que le serveur a vu (et les gestes écrasés par collapse) quitte la file.
          var done = Outbox.answeredIds(body.results).concat(stored.map(function (op) { return op.id; }));
          return queue.remove(done).then(function () {
            attempt = 0;
            reconcile(body);
            status("");
          });
        });
      }
      if (verdict === "auth") {
        status("Reconnexion requise pour synchroniser. " + describePending(stored.length), true);
        return null;
      }
      if (verdict === "drop") {
        return queue.remove(stored.map(function (op) { return op.id; }));
      }
      scheduleRetry();
      return null;
    });
  }

  function scheduleRetry() {
    clearTimeout(retryTimer);
    retryTimer = setTimeout(flush, Outbox.backoff(attempt++));
  }

  function registerBackgroundSync() {
    // Facultatif (Chrome, Android) : ne doit jamais conditionner la synchronisation elle-même.
    if (!navigator.serviceWorker || !navigator.serviceWorker.getRegistration) {
      return;
    }
    navigator.serviceWorker
      .getRegistration()
      .then(function (registration) {
        return registration && registration.sync && registration.sync.register("cookup-sync");
      })
      .catch(function () {});
  }

  function enqueue(operation) {
    return queue
      .put(operation)
      .then(function () {
        return queue.all();
      })
      .then(function (stored) {
        if (!navigator.onLine) {
          status("Hors ligne. " + describePending(stored.length));
        }
        registerBackgroundSync();
        return flush();
      });
  }

  /* ---------- Page « courses » ---------- */
  function setupShopping() {
    var root = document.querySelector("[data-shopping]");
    if (!root) {
      return;
    }
    root.addEventListener("submit", function (event) {
      var form = event.target;
      var action = form.dataset.action;
      var li = form.closest("[data-item]");
      if (action === "toggle" && li) {
        event.preventDefault();
        var current = li.dataset.checked ? li.dataset.checked === "1" : li.classList.contains("done");
        var checked = !current;
        paintChecked(li, checked);
        enqueue(Outbox.makeOperation("set", li.dataset.item, { checked: checked }, Date.now()));
      } else if (action === "remove" && li) {
        event.preventDefault();
        li.hidden = true;
        enqueue(Outbox.makeOperation("remove", li.dataset.item, {}, Date.now()));
      } else if (action === "add" && !navigator.onLine) {
        event.preventDefault();
        addOffline(form);
      }
    });
    queue.all().then(function (stored) {
      applyPending(stored);
      if (stored.length && !navigator.onLine) {
        status("Hors ligne. " + describePending(stored.length));
      }
      return flush();
    });
  }

  function addOffline(form) {
    var data = new FormData(form);
    var label = String(data.get("label") || "").trim();
    if (!label) {
      return;
    }
    var id = Outbox.newId();
    var quantity = String(data.get("quantity") || "");
    var operation = Outbox.makeOperation(
      "add", id, { label: label, quantity: quantity, aisle: data.get("aisle") || "misc" }, Date.now()
    );
    var item = document.createElement("li");
    item.dataset.item = id;
    item.textContent = label + (quantity ? " — " + quantity : "") + " (ajouté hors ligne)";
    form.parentNode.insertBefore(item, form);
    form.reset();
    enqueue(operation);
  }

  /* ---------- Déconnexion ---------- */
  function clearLocalData() {
    var cleared = [queue.clear()];
    if (self.caches) {
      cleared.push(caches.delete(PAGES_CACHE));
    }
    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
      navigator.serviceWorker.controller.postMessage({ type: "clear" });
    }
    return Promise.all(cleared).catch(function () {});
  }

  function setupLogout() {
    document.addEventListener("submit", function (event) {
      var form = event.target;
      if (!form.action || !/\/deconnexion$/.test(new URL(form.action, location.href).pathname)) {
        return;
      }
      event.preventDefault();
      queue
        .all()
        .then(function (stored) {
          return navigator.onLine && stored.length ? flush().then(queue.all) : stored;
        })
        .then(function (stored) {
          if (stored.length && !confirm(describePending(stored.length) + " Se déconnecter les efface. Continuer ?")) {
            return null;
          }
          return clearLocalData().then(function () {
            if (navigator.onLine) {
              form.submit();
            } else {
              // Impossible de fermer la session côté serveur : on le fera au retour du réseau.
              localStorage.setItem(LOGOUT_FLAG, "1");
              location.href = "/hors-ligne";
            }
          });
        });
    });
    window.addEventListener("online", finishPendingLogout);
    finishPendingLogout();
  }

  function finishPendingLogout() {
    if (!navigator.onLine || localStorage.getItem(LOGOUT_FLAG) !== "1") {
      return;
    }
    fetch("/deconnexion", {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken(null) },
    }).then(function (response) {
      if (response.ok || response.redirected || response.type === "opaqueredirect") {
        localStorage.removeItem(LOGOUT_FLAG);
        location.href = "/connexion";
      }
    }).catch(function () {});
  }

  /* ---------- Démarrage ---------- */
  function start() {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {});
      navigator.serviceWorker.addEventListener("message", function (event) {
        if (event.data && event.data.type === "flush") {
          flush();
        }
      });
    }
    window.addEventListener("online", function () {
      status("");
      flush();
    });
    window.addEventListener("offline", function () {
      queue.all().then(function (stored) {
        status("Hors ligne. " + (stored.length ? describePending(stored.length) : "Vos cases cochées seront synchronisées au retour du réseau."));
      });
    });
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible") {
        flush();
      }
    });
    setupShopping();
    setupLogout();
  }

  if (!self.indexedDB || !Outbox) {
    return;
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
