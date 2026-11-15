// Pruebas de la lógica del frontend: node --test tests/js/
const test = require("node:test");
const assert = require("node:assert/strict");
const C = require("../../src/radar/web/static/radar-core.js");

const today = new Date(2026, 10, 15);
const fx = { "€": 1, "$": 0.86 };
const mk = (o) => ({ section: "robots", verdict: "ok", rank: 1, currency: "€", tags: [], highlights: [], note: "", info: "", store: "", ...o });
const A = mk({ id: "a", name: "Dreame Aqua10 Ultra Roller", note: "Fregado con rodillo", price: 575, rank: 2, discount_pct: 48, ends_on: "2026-11-30", below_annual_low: true, vs_annual_low_pct: -28 });
const B = mk({ id: "b", name: "Roborock Qrevo", note: "Mopas giratorias", price: 299, rank: 1, verdict: "pasa", discount_pct: 57 });
const U = mk({ id: "u", section: "print", name: "Snapmaker U1", currency: "$", price: 560, rank: 1, live: { offer_vs_market_pct: -30 } });
const N = mk({ id: "n", section: "print", name: "Filamento", price: null, rank: 2, discount_pct: 47, ends_on: "2026-12-01", live: { offer_vs_market_pct: -5 } });
const ALL = [A, B, U, N];
const ids = (r) => r.map((d) => d.id);
const ctx = { today, fx, sectionTitles: { robots: "Robots aspiradores", print: "Impresión 3D" } };

test("normaliza tildes, mayúsculas y espacios", () => {
  assert.equal(C.normalize("  Impresión   3D ÚLTIMA "), "impresion 3d ultima");
});

test("búsqueda multi-término, sin tildes, en cualquier campo y en el título de la sección", () => {
  assert.deepEqual(ids(C.query(ALL, { q: "dreame RODILLO" }, ctx)), ["a"]);
  assert.deepEqual(ids(C.query(ALL, { q: "giratórias" }, ctx)), ["b"]);
  assert.deepEqual(ids(C.query(ALL, { q: "impresion" }, ctx)).sort(), ["n", "u"]);
  assert.deepEqual(ids(C.query(ALL, { q: "dreame mopas" }, ctx)), []);
});

test("precio máximo en euros, conservando las ofertas sin precio", () => {
  assert.deepEqual(ids(C.query(ALL, { max: 490 }, ctx)).sort(), ["b", "n", "u"]);
});

test("grupos de veredicto y solo bajo mínimo anual", () => {
  assert.deepEqual(ids(C.query(ALL, { verdict: "skip" }, ctx)), ["b"]);
  assert.deepEqual(ids(C.query(ALL, { real: true }, ctx)), ["a"]);
  assert.throws(() => C.query(ALL, { verdict: "nope" }, ctx));
});

test("ordenaciones", () => {
  assert.deepEqual(ids(C.query(ALL, { sort: "disc" }, ctx)), ["b", "a", "n", "u"]);
  assert.deepEqual(ids(C.query(ALL, { sort: "price" }, ctx)), ["b", "u", "a", "n"]);
  assert.deepEqual(ids(C.query(ALL, { sort: "end" }, ctx)), ["a", "n", "b", "u"]);
  assert.deepEqual(ids(C.query(ALL, { sort: "market", sec: "print" }, ctx)), ["u", "n"]);
  assert.throws(() => C.query(ALL, { sort: "nope" }, ctx));
});

test("días restantes con fecha local", () => {
  assert.equal(C.daysLeft("2026-11-30", today), 15);
  assert.equal(C.daysLeft("2026-11-14", today), -1);
  assert.equal(C.daysLeft(null, today), null);
});
