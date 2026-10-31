/* Logique pure de la file d'attente hors ligne (sans DOM ni réseau) : testée avec node. */
(function (root) {
  "use strict";

  function newId() {
    if (root.crypto && root.crypto.randomUUID) {
      return root.crypto.randomUUID();
    }
    // Repli pour les anciens navigateurs : identifiant v4 construit à la main.
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
    });
  }

  /** Une opération = un geste de l'utilisateur, horodaté à l'instant du geste (pas de l'envoi). */
  function makeOperation(type, itemId, fields, now, idFactory) {
    var operation = { id: (idFactory || newId)(), type: type, item: itemId, ts: now };
    for (var key in fields || {}) {
      operation[key] = fields[key];
    }
    return operation;
  }

  /** Réduit la file : le dernier « set » d'une ligne suffit ; ajout puis retrait s'annulent. */
  function collapse(operations) {
    var ordered = operations.slice().sort(function (a, b) {
      return a.ts - b.ts;
    });
    var cancelled = {};
    ordered.forEach(function (op) {
      if (op.type === "remove" && ordered.some(function (o) { return o.type === "add" && o.item === op.item; })) {
        cancelled[op.item] = true;
      }
    });
    var lastSet = {};
    ordered.forEach(function (op) {
      if (op.type === "set") {
        lastSet[op.item] = op.id;
      }
    });
    return ordered.filter(function (op) {
      if (cancelled[op.item]) {
        return false;
      }
      return op.type !== "set" || lastSet[op.item] === op.id;
    });
  }

  /** État à afficher pour une ligne : le dernier geste local en attente prime sur la page. */
  function pendingState(operations) {
    var state = {};
    collapse(operations).forEach(function (op) {
      if (op.type === "set") {
        state[op.item] = { checked: op.checked };
      } else if (op.type === "remove") {
        state[op.item] = { removed: true };
      }
    });
    return state;
  }

  /** Que faire d'une réponse : ok, réessayer plus tard, se reconnecter, ou abandonner. */
  function classify(status) {
    if (status === 200) {
      return "ok";
    }
    if (status === 0 || status === 429 || status >= 500) {
      return "retry";
    }
    if (status === 401 || status === 403 || status === 302) {
      return "auth";
    }
    return "drop";
  }

  /** Délai avant nouvel essai : 2 s, 4 s, 8 s… plafonné à 5 minutes. */
  function backoff(attempt) {
    return Math.min(300000, 2000 * Math.pow(2, Math.max(0, attempt)));
  }

  /** Les identifiants pour lesquels le serveur a répondu (quel que soit le statut) quittent la file. */
  function answeredIds(results) {
    return (results || []).map(function (r) {
      return r.id;
    });
  }

  var api = {
    newId: newId,
    makeOperation: makeOperation,
    collapse: collapse,
    pendingState: pendingState,
    classify: classify,
    backoff: backoff,
    answeredIds: answeredIds,
  };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.CookupOutbox = api;
})(typeof self !== "undefined" ? self : this);
