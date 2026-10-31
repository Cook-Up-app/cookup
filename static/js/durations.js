/* Durées des étapes de recette (« 10 minutes », « 5 à 8 min », « 1 h 30 ») : logique pure. */
(function (root) {
  "use strict";

  // « 1 h 30 » : après des heures, deux chiffres (ou un nombre suivi de « min ») comptent en minutes,
  // sauf s'ils sont suivis d'une unité de quantité (« 2 heures 15 g »).
  var DURATION = new RegExp(
    "(\\d+)\\s*(?:à\\s*(\\d+)\\s*)?(heures?|h|minutes?|min|secondes?|sec|s)\\b" +
      "(?:\\s*(\\d{2}\\b|\\d{1,2}(?=\\s*(?:minutes?|min)\\b))(?:\\s*(?:minutes?|min)\\b)?(?!\\s*(?:g|kg|ml|cl|l|°|%)))?",
    "gi"
  );

  /** Secondes de chaque durée de la phrase ; une fourchette garde sa borne haute. */
  function find(text) {
    var found = [];
    var match;
    DURATION.lastIndex = 0;
    while ((match = DURATION.exec(text)) !== null) {
      var amount = parseInt(match[2] || match[1], 10);
      var unit = match[3].toLowerCase().charAt(0);
      var seconds = unit === "h" ? amount * 3600 : unit === "m" ? amount * 60 : amount;
      if (match[4] && unit === "h") {
        seconds += parseInt(match[4], 10) * 60; // « 1 h 30 »
      }
      found.push({ label: match[0].trim(), seconds: seconds });
    }
    return found;
  }

  function format(totalSeconds) {
    var hours = Math.floor(totalSeconds / 3600);
    var minutes = Math.floor((totalSeconds % 3600) / 60);
    var seconds = totalSeconds % 60;
    var tail = (minutes < 10 && hours ? "0" : "") + minutes + ":" + (seconds < 10 ? "0" : "") + seconds;
    return hours ? hours + ":" + tail : tail;
  }

  var api = { find: find, format: format };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.CookupDurations = api;
})(typeof self !== "undefined" ? self : this);
