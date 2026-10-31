/* Mode cuisine : une étape à la fois en grand texte, minuteurs, écran maintenu allumé.
   Sans JavaScript, la page reste une simple liste d'étapes lisible. */
(function () {
  "use strict";

  var root = document.querySelector("[data-kitchen]");
  if (!root || !self.CookupDurations) {
    return;
  }

  var steps = Array.prototype.slice.call(root.querySelectorAll("[data-step]"));
  var counter = root.querySelector("[data-counter]");
  var previous = root.querySelector("[data-prev]");
  var next = root.querySelector("[data-next]");
  var timers = root.querySelector("[data-timers]");
  var current = 0;
  var wakeLock = null;
  var Durations = self.CookupDurations;

  /* ---------- Étapes ---------- */
  function show(index) {
    current = Math.max(0, Math.min(steps.length - 1, index));
    steps.forEach(function (step, i) {
      step.hidden = i !== current;
    });
    counter.textContent = "Étape " + (current + 1) + " sur " + steps.length;
    previous.disabled = current === 0;
    next.disabled = current === steps.length - 1;
    offerTimers(steps[current].textContent);
  }

  function offerTimers(text) {
    timers.querySelectorAll("[data-offer]").forEach(function (node) {
      node.remove();
    });
    Durations.find(text).forEach(function (duration) {
      var button = document.createElement("button");
      button.type = "button";
      button.dataset.offer = "1";
      button.textContent = "Minuteur : " + duration.label;
      button.addEventListener("click", function () {
        startTimer(duration);
      });
      timers.appendChild(button);
    });
  }

  /* ---------- Minuteurs ---------- */
  function startTimer(duration) {
    var end = Date.now() + duration.seconds * 1000;
    var box = document.createElement("p");
    box.className = "timer";
    box.setAttribute("role", "timer");
    var cancel = document.createElement("button");
    cancel.type = "button";
    cancel.textContent = "Arrêter";
    box.appendChild(document.createElement("span"));
    box.appendChild(cancel);
    timers.appendChild(box);
    var tick = setInterval(function () {
      var left = Math.max(0, Math.round((end - Date.now()) / 1000));
      box.firstChild.textContent = duration.label + " — " + Durations.format(left) + " ";
      if (left === 0) {
        clearInterval(tick);
        box.classList.add("ring");
        box.firstChild.textContent = duration.label + " — terminé ! ";
        if (navigator.vibrate) {
          navigator.vibrate([300, 150, 300]);
        }
      }
    }, 500);
    cancel.addEventListener("click", function () {
      clearInterval(tick);
      box.remove();
    });
  }

  /* ---------- Écran allumé (API Wake Lock) ---------- */
  function keepAwake() {
    if (!("wakeLock" in navigator)) {
      return;
    }
    navigator.wakeLock.request("screen").then(function (lock) {
      wakeLock = lock;
    }).catch(function () {});
  }

  document.addEventListener("visibilitychange", function () {
    // Le verrou saute quand la page passe en arrière-plan : on le reprend au retour.
    if (document.visibilityState === "visible" && (!wakeLock || wakeLock.released)) {
      keepAwake();
    }
  });

  /* ---------- Démarrage ---------- */
  root.classList.add("kitchen-active");
  previous.addEventListener("click", function () {
    show(current - 1);
  });
  next.addEventListener("click", function () {
    show(current + 1);
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "ArrowRight") {
      show(current + 1);
    } else if (event.key === "ArrowLeft") {
      show(current - 1);
    }
  });
  show(0);
  keepAwake();
})();
