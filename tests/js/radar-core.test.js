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

test("la búsqueda encuentra por tienda de options e idealo", () => {
  const M = mk({ id: "m", name: "Dreame X50", store: "Dreame ES", options: [{ store: "PcComponentes", price: 600, currency: "€" }] });
  assert.deepEqual(ids(C.query([...ALL, M], { q: "pccomponentes" }, ctx)), ["m"]);
  assert.deepEqual(ids(C.query([...ALL, M], { q: "pccomponentés x50" }, ctx)), ["m"]);
  assert.deepEqual(ids(C.query([...ALL, M], { q: "fnac" }, ctx)), []);
});

test("storeKey normaliza nombres de tienda", () => {
  assert.equal(C.storeKey("www.PcComponentes.com"), C.storeKey("PcComponentes"));
  assert.equal(C.storeKey("El Corte Inglés"), C.storeKey("elcorteingles.es"));
  assert.equal(C.storeKey("Dreame ES (tienda oficial)"), "dreame");
});

test("storeRows une principal, options e idealo, ordena por precio en € y marca la más barata", () => {
  const d = mk({ id: "x", store: "Dreame ES", price: 599, link: "https://d.es/x", tracking: { url: "https://www.idealo.es/p" },
    options: [{ store: "MediaMarkt", price: 579, currency: "€", url: "https://mm.es/x", checked_on: "2026-11-15", note: "" },
              { store: "US Shop", price: 700, currency: "$", url: "https://us/x", checked_on: null },
              { store: "Sin precio", price: null, currency: "€", url: "https://sp/x" }],
    live: { at: "2026-11-15T10:00", shops: [{ shop: "carrefour.es", price: 560 }, { shop: "www.mediamarkt.es", price: 570 }] } });
  const rows = C.storeRows(d, fx);
  assert.deepEqual(rows.map((r) => r.store), ["carrefour.es", "MediaMarkt", "Dreame ES", "US Shop", "Sin precio"]);
  // mediamarkt: editorial 579 vs idealo 570 → gana el más barato (idealo)
  assert.equal(rows[1].kind, "idealo");
  assert.equal(rows[1].price, 570);
  assert.deepEqual(rows.map((r) => r.best), [true, false, false, false, false]);
  assert.equal(rows[3].eur, 700 * 0.86);
  assert.equal(rows[0].kind, "idealo");
  assert.equal(rows[2].kind, "main");
  assert.equal(rows[4].eur, null);
  assert.equal(C.storeCount(d), 5);
});

test("storeRows con empate prefiere la fila editorial y sin extras devuelve solo la principal", () => {
  const d = mk({ id: "y", store: "Carrefour", price: 100, link: "https://c/x", live: { shops: [{ shop: "carrefour.es", price: 100 }] } });
  const rows = C.storeRows(d, fx);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].kind, "main");
  assert.equal(C.storeRows(mk({ id: "z", store: "A", price: null }), fx).length, 1);
});

test("isMajorShop distingue grandes tiendas y tiendas oficiales de tiendas pequeñas", () => {
  for (const s of ["pccomponentes.com", "Mediamarkt.es", "amazon.es", "carrefour.es", "El Corte Inglés", "fnac.es",
                   "Neobyte.es", "es.roborock.com", "Samsung.com/es", "sony.es", "Apple Store ES", "Simufy.com", "3djake.es"])
    assert.equal(C.isMajorShop(s), true, s);
  for (const s of ["zomvy.com", "movilines.com", "bixoto.com/es", "electropolis.es", "Ocasionia", "Amazon Marketplace (ES)"])
    assert.equal(C.isMajorShop(s), false, s);
});

test("storeRows marca como pequeñas solo las filas de idealo de tiendas no conocidas", () => {
  const d = { store: "Tienda Rara", price: 100, currency: "€", link: "https://x", options: [],
              live: { at: "2026-11-15T20:00", shops: [{ shop: "zomvy.com", price: 80 }, { shop: "amazon.es", price: 99 }] },
              tracking: { url: "https://www.idealo.es/precios/1/x.html" } };
  const rows = C.storeRows(d, { "€": 1 });
  assert.deepEqual(rows.map((r) => [r.store, r.small]), [["zomvy.com", true], ["amazon.es", false], ["Tienda Rara", false]]);
});
