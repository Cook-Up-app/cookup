/* Export de la liste de courses : copie en texte brut, partage système, impression.
   Le texte est construit depuis la page (donc disponible hors ligne). */
(function (root) {
  "use strict";

  /** Texte brut : un titre, puis les rayons et leurs articles restant à acheter. */
  function buildText(title, sections, includeChecked) {
    var lines = [title];
    sections.forEach(function (section) {
      var items = section.items.filter(function (item) {
        return includeChecked || !item.checked;
      });
      if (!items.length) {
        return;
      }
      lines.push("", section.aisle);
      items.forEach(function (item) {
        lines.push("- " + item.label + (item.quantity ? " — " + item.quantity : "") + (item.checked ? " (pris)" : ""));
      });
    });
    return lines.join("\n");
  }

  var api = { buildText: buildText };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.CookupExport = api;

  if (typeof document === "undefined") {
    return;
  }

  function collect() {
    return Array.prototype.map.call(document.querySelectorAll("[data-shopping] details"), function (block) {
      var heading = block.querySelector("summary h2");
      return {
        aisle: heading ? heading.textContent.trim() : "",
        items: Array.prototype.filter
          .call(block.querySelectorAll("[data-item]"), function (li) {
            return !li.hidden;
          })
          .map(function (li) {
            var text = (li.querySelector("span") || li).textContent.replace(/\s+/g, " ").trim();
            var parts = text.split(" — ");
            return {
              label: parts[0].replace(/\s*\(facultatif\)$/, ""),
              quantity: parts.slice(1).join(" — ").replace(/\s*\(facultatif\)$/, ""),
              checked: li.classList.contains("done"),
            };
          }),
      };
    });
  }

  function currentText() {
    var title = (document.querySelector("h1") || {}).textContent || "Liste de courses";
    return buildText(title.trim(), collect(), false);
  }

  function flash(button, message) {
    var original = button.textContent;
    button.textContent = message;
    setTimeout(function () {
      button.textContent = original;
    }, 2000);
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-export]");
    if (!button) {
      return;
    }
    var action = button.dataset.export;
    if (action === "print") {
      window.print();
    } else if (action === "copy" && navigator.clipboard) {
      navigator.clipboard.writeText(currentText()).then(function () {
        flash(button, "Copié !");
      }, function () {
        flash(button, "Copie impossible");
      });
    } else if (action === "share" && navigator.share) {
      navigator.share({ title: "Liste de courses", text: currentText() }).catch(function () {});
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    // Le partage système n'existe pas partout : on masque le bouton plutôt que de le laisser inerte.
    if (!navigator.share) {
      document.querySelectorAll('[data-export="share"]').forEach(function (button) {
        button.hidden = true;
      });
    }
    if (!navigator.clipboard) {
      document.querySelectorAll('[data-export="copy"]').forEach(function (button) {
        button.hidden = true;
      });
    }
  });
})(typeof self !== "undefined" ? self : this);
