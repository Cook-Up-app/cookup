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

  // Filtre de pastilles (début de mot) : <div data-filter-scope>, <input data-filter-input>, <label class="chip">.
  function fold(text) {
    return text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  }

  document.querySelectorAll("[data-filter-scope]").forEach(function (scope) {
    var input = scope.querySelector("[data-filter-input]");
    if (!input) {
      return;
    }
    input.addEventListener("input", function () {
      var needle = fold(input.value.trim());
      scope.querySelectorAll(".chip").forEach(function (chip) {
        chip.hidden = needle !== "" && (" " + fold(chip.textContent)).indexOf(" " + needle) === -1;
      });
      scope.querySelectorAll(".filter-group").forEach(function (group) {
        group.hidden = !group.querySelector(".chip:not([hidden])");
      });
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
