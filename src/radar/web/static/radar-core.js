/* Lógica pura del radar (filtros, búsqueda, ordenación). Sin DOM: se prueba con node --test. */
(function (root, factory) {
  const core = factory();
  if (typeof module === "object" && module.exports) module.exports = core;
  else root.RadarCore = core;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const VERDICT_GROUPS = {
    all: ["top", "ok", "pasa", "no"],
    buy: ["top", "ok"],
    top: ["top"],
    skip: ["pasa", "no"],
  };
  const BIG = 1e9;

  function normalize(s) {
    return String(s == null ? "" : s)
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();
  }

  function terms(q) {
    const n = normalize(q);
    return n ? n.split(" ") : [];
  }

  function haystack(d, sectionTitle) {
    return normalize([d.name, d.store, d.note, d.info, sectionTitle || "", ...(d.tags || []), ...(d.highlights || [])].join(" "));
  }

  function matchesAll(hay, ts) {
    return ts.every((t) => hay.includes(t));
  }

  function priceEur(d, fx) {
    if (d.price == null) return null;
    const rate = fx && fx[d.currency] != null ? fx[d.currency] : 1;
    return d.price * rate;
  }

  function daysLeft(endsOn, today) {
    if (!endsOn) return null;
    const a = Date.UTC(+endsOn.slice(0, 4), +endsOn.slice(5, 7) - 1, +endsOn.slice(8, 10));
    const b = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
    return Math.round((a - b) / 86400000);
  }

  function sortKey(sort, d, today, fx) {
    switch (sort) {
      case "rec": return d.rank;
      case "disc": return d.discount_pct == null ? BIG : -d.discount_pct;
      case "low": return d.vs_annual_low_pct == null ? BIG : d.vs_annual_low_pct;
      case "price": { const p = priceEur(d, fx); return p == null ? BIG : p; }
      case "end": { const n = daysLeft(d.ends_on, today); return n == null || n < 0 ? BIG : n; }
      case "market": return d.live && d.live.offer_vs_market_pct != null ? d.live.offer_vs_market_pct : BIG;
      default: throw new Error("Orden desconocido: " + sort);
    }
  }

  /**
   * Filtra y ordena. state: {sec, q, verdict, sort, max (null = sin límite), real}.
   * Devuelve las ofertas ordenadas dentro de su sección (el orden de secciones lo decide quien pinta).
   */
  function query(offers, state, ctx) {
    const today = ctx.today, fx = ctx.fx || {}, titles = ctx.sectionTitles || {};
    const allowed = VERDICT_GROUPS[state.verdict || "all"];
    if (!allowed) throw new Error("Grupo de veredicto desconocido: " + state.verdict);
    const ts = terms(state.q);
    const out = offers.filter((d) => {
      if (state.sec && state.sec !== "all" && d.section !== state.sec) return false;
      if (!allowed.includes(d.verdict)) return false;
      if (ts.length && !matchesAll(haystack(d, titles[d.section]), ts)) return false;
      if (state.max != null) { const p = priceEur(d, fx); if (p != null && p > state.max) return false; }
      if (state.real && !d.below_annual_low) return false;
      return true;
    });
    const sort = state.sort || "rec";
    sortKey(sort, offers[0] || { rank: 0 }, today, fx); // valida el orden aunque no haya resultados
    return out
      .map((d) => ({ d, k: sortKey(sort, d, today, fx) }))
      .sort((a, b) => (a.k - b.k) || (a.d.rank - b.d.rank))
      .map((x) => x.d);
  }

  return { normalize, terms, haystack, matchesAll, priceEur, daysLeft, query, VERDICT_GROUPS };
});
