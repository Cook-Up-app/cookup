const test = require("node:test");
const assert = require("node:assert/strict");
const { buildText } = require("../../static/js/export.js");

const sections = [
  { aisle: "Fruits et légumes", items: [{ label: "courgette", quantity: "4", checked: false }, { label: "citron", quantity: "", checked: true }] },
  { aisle: "Crèmerie", items: [{ label: "crème liquide", quantity: "1 brique de 200 ml (≈ 200 ml)", checked: false }] },
  { aisle: "Surgelés", items: [{ label: "épinards", quantity: "300 g", checked: true }] },
];

test("liste les articles restant à acheter, par rayon", () => {
  assert.equal(
    buildText("Liste de courses", sections, false),
    ["Liste de courses", "", "Fruits et légumes", "- courgette — 4", "", "Crèmerie", "- crème liquide — 1 brique de 200 ml (≈ 200 ml)"].join("\n")
  );
});

test("un rayon entièrement coché n'apparaît pas", () => {
  assert.ok(!buildText("T", sections, false).includes("Surgelés"));
});

test("on peut inclure les articles déjà pris, signalés", () => {
  const text = buildText("T", sections, true);
  assert.ok(text.includes("- citron (pris)"));
  assert.ok(text.includes("- épinards — 300 g (pris)"));
});

test("une liste vide se réduit au titre", () => {
  assert.equal(buildText("Courses", [], false), "Courses");
});
