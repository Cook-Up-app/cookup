/* Petits comportements d'interface, sans dépendance : affichage des curseurs, confirmations. */
(function () {
  "use strict";

  function syncRange(input) {
    var output = document.getElementById(input.id + "_value");
    if (output) {
      output.textContent = input.value + " %";
    }
  }

  document.querySelectorAll('input[type="range"]').forEach(function (input) {
    syncRange(input);
    input.addEventListener("input", function () {
      syncRange(input);
    });
  });

  // <form data-confirm="Supprimer ?"> : demande confirmation avant d'envoyer (actions destructrices).
  document.addEventListener("submit", function (event) {
    var message = event.target.dataset && event.target.dataset.confirm;
    if (message && !window.confirm(message)) {
      event.preventDefault();
    }
  });
})();
