const test = require("node:test");
const assert = require("node:assert/strict");
const durations = require("../../static/js/durations.js");

test("trouve une durée en minutes", () => {
  assert.deepEqual(durations.find("Cuire 10 minutes à feu doux."), [{ label: "10 minutes", seconds: 600 }]);
});

test("une fourchette garde la borne haute", () => {
  assert.equal(durations.find("Laisser cuire 5 à 8 min")[0].seconds, 480);
});

test("heures, secondes et abréviations", () => {
  assert.equal(durations.find("Réserver 2 heures au frais")[0].seconds, 7200);
  assert.equal(durations.find("Mixer 30 secondes")[0].seconds, 30);
  assert.equal(durations.find("Cuire 45 min")[0].seconds, 2700);
});

test("« 1 h 30 » vaut une heure et demie", () => {
  assert.equal(durations.find("Rôtir 1 h 30 en arrosant")[0].seconds, 5400);
});

test("plusieurs durées dans une même étape", () => {
  const found = durations.find("Saisir 3 minutes par face, puis laisser reposer 10 minutes.");
  assert.deepEqual(found.map((d) => d.seconds), [180, 600]);
});

test("aucune durée, aucun minuteur", () => {
  assert.deepEqual(durations.find("Couper les courgettes en rondelles."), []);
  assert.deepEqual(durations.find("Préchauffer le four à 180 °C."), []);
});

test("les quantités ne sont pas prises pour des durées", () => {
  assert.deepEqual(durations.find("Ajouter 200 g de farine et 3 œufs."), []);
});

test("format affiche minutes:secondes et heures", () => {
  assert.equal(durations.format(65), "1:05");
  assert.equal(durations.format(600), "10:00");
  assert.equal(durations.format(3725), "1:02:05");
  assert.equal(durations.format(0), "0:00");
});
