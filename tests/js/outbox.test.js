const test = require("node:test");
const assert = require("node:assert/strict");
const outbox = require("../../static/js/outbox.js");

let counter = 0;
const ids = () => "op" + ++counter;
const set = (item, checked, ts) => ({ id: ids(), type: "set", item, checked, ts });

test("makeOperation horodate au geste et garde les champs", () => {
  const op = outbox.makeOperation("add", "i1", { label: "Piles", aisle: "misc" }, 1234, () => "fixed");
  assert.deepEqual(op, { id: "fixed", type: "add", item: "i1", ts: 1234, label: "Piles", aisle: "misc" });
});

test("newId produit des identifiants uniques de forme UUID", () => {
  const a = outbox.newId();
  const b = outbox.newId();
  assert.notEqual(a, b);
  assert.match(a, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});

test("collapse ne garde que le dernier set d'une ligne", () => {
  const ops = [set("a", true, 1), set("a", false, 2), set("a", true, 3), set("b", true, 2)];
  const kept = outbox.collapse(ops);
  assert.deepEqual(kept.map((o) => [o.item, o.checked, o.ts]), [["b", true, 2], ["a", true, 3]]);
});

test("collapse remet les opérations dans l'ordre des gestes", () => {
  const kept = outbox.collapse([set("a", true, 30), set("b", true, 10), set("c", true, 20)]);
  assert.deepEqual(kept.map((o) => o.item), ["b", "c", "a"]);
});

test("un ajout suivi d'un retrait s'annule entièrement", () => {
  const ops = [
    { id: ids(), type: "add", item: "n", ts: 1, label: "x", aisle: "misc" },
    set("n", true, 2),
    { id: ids(), type: "remove", item: "n", ts: 3 },
    set("z", true, 4),
  ];
  assert.deepEqual(outbox.collapse(ops).map((o) => o.item), ["z"]);
});

test("un retrait sans ajout correspondant est conservé", () => {
  const ops = [{ id: ids(), type: "remove", item: "auto", ts: 1 }];
  assert.equal(outbox.collapse(ops).length, 1);
});

test("collapse ne modifie pas le tableau d'origine", () => {
  const ops = [set("a", true, 2), set("a", false, 1)];
  outbox.collapse(ops);
  assert.equal(ops.length, 2);
  assert.equal(ops[0].ts, 2);
});

test("pendingState : le dernier geste local prime, un retrait masque la ligne", () => {
  const state = outbox.pendingState([set("a", true, 1), set("a", false, 2), { id: ids(), type: "remove", item: "b", ts: 3 }]);
  assert.deepEqual(state, { a: { checked: false }, b: { removed: true } });
});

test("classify distingue succès, réessai, reconnexion et abandon", () => {
  assert.equal(outbox.classify(200), "ok");
  assert.equal(outbox.classify(0), "retry");
  assert.equal(outbox.classify(503), "retry");
  assert.equal(outbox.classify(429), "retry");
  assert.equal(outbox.classify(403), "auth");
  assert.equal(outbox.classify(401), "auth");
  assert.equal(outbox.classify(302), "auth");
  assert.equal(outbox.classify(400), "drop");
  assert.equal(outbox.classify(404), "drop");
});

test("backoff double le délai jusqu'à 5 minutes", () => {
  assert.equal(outbox.backoff(0), 2000);
  assert.equal(outbox.backoff(1), 4000);
  assert.equal(outbox.backoff(3), 16000);
  assert.equal(outbox.backoff(30), 300000);
  assert.equal(outbox.backoff(-5), 2000);
});

test("answeredIds liste les opérations acquittées par le serveur", () => {
  assert.deepEqual(outbox.answeredIds([{ id: "a", status: "applied" }, { id: "b", status: "missing" }]), ["a", "b"]);
  assert.deepEqual(outbox.answeredIds(undefined), []);
});
