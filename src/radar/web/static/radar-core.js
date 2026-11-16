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
    return normalize([d.name, d.store, d.note, d.info, sectionTitle || "", ...(d.tags || []), ...(d.highlights || []), ...(d.options || []).map((o) => o.store), ...Object.values(d.facets || {})].join(" "));
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

  /** Clave estable de tienda: «www.PcComponentes.com» y «PcComponentes» coinciden (igual que domain/text.py). */
  function storeKey(name) {
    let s = normalize(String(name == null ? "" : name).replace(/\([^)]*\)/g, " "));
    s = s.replace(/^www\./, "").replace(/\.(es|com|eu|net|org|de|fr|it|pt|co\.uk)$/, "").replace(/\s+es$/, "");
    return s.replace(/[\s.\-_]+/g, "");
  }

  // Cadenas grandes y especialistas conocidos en España/UE. El resto de tiendas que lista idealo (importadores de
  // móviles, tiendas online pequeñas) se muestran igual, pero marcadas para que el lector mire opiniones y garantía.
  const MAJOR_SHOPS = ["pccomponentes", "mediamarkt", "amazon", "carrefour", "elcorteingles", "fnac", "worten",
    "coolmod", "neobyte", "lidl", "conforama", "electrodepot", "alternate", "ldlc", "reichelt", "3djake", "simufy",
    "redcomputer", "lifeinformatica", "aussar", "vibbo", "decathlon", "eci", "apple", "samsung", "sony", "xiaomi",
    "roborock", "irobot", "dreame", "ecovacs", "moza", "fanatec", "bambulab", "elegoo", "anycubic", "minisforum",
    "lenovo", "hp", "dell", "asus", "logitech", "meta", "google"];
  const BRAND_STORE = /\b(oficial|official|store)\b|^es\./i;

  function isMajorShop(name) {
    const raw = String(name == null ? "" : name);
    if (/marketplace/i.test(raw)) return false;
    const k = storeKey(raw.replace(/\/.*$/, ""));
    return MAJOR_SHOPS.some((m) => k === m || k.startsWith(m)) || (BRAND_STORE.test(raw) && MAJOR_SHOPS.some((m) => k.includes(m)));
  }

  const KIND_ORDER = { main: 0, option: 1, idealo: 2 };

  /**
   * Una fila por tienda: oferta principal, options editoriales y tiendas de idealo (live.shops).
   * Si una tienda aparece varias veces gana el precio más barato (a igualdad, la editorial) y se conserva el
   * nombre editorial. Orden por precio en € (sin precio al final); best = la más barata.
   */
  function storeRows(d, fx) {
    const rate = (c) => (fx && fx[c] != null ? fx[c] : 1);
    const eur = (p, c) => (p == null ? null : p * rate(c));
    const cand = [{ store: d.store, price: d.price, currency: d.currency, url: d.link, kind: "main", checked_on: null, note: "" }];
    for (const o of d.options || []) cand.push({ store: o.store, price: o.price, currency: o.currency || "€", url: o.url, kind: "option", checked_on: o.checked_on || null, note: o.note || "" });
    const at = d.live && d.live.at;
    const itrack = d.tracking && d.tracking.url;
    for (const s of (d.live && d.live.shops) || []) cand.push({ store: s.shop, price: s.price, currency: "€", url: itrack || "", kind: "idealo", checked_on: null, note: "", at });
    const rank = (r) => [r.eur == null ? 1 : 0, r.eur == null ? 0 : r.eur, KIND_ORDER[r.kind]];
    const cmp = (a, b) => { const x = rank(a), y = rank(b); return x[0] - y[0] || x[1] - y[1] || x[2] - y[2]; };
    const byKey = new Map();
    for (const c of cand) {
      c.eur = eur(c.price, c.currency);
      const k = storeKey(c.store), prev = byKey.get(k);
      if (!prev) { byKey.set(k, c); continue; }
      const win = cmp(c, prev) < 0 ? c : prev;
      win.store = prev.kind !== "idealo" ? prev.store : (c.kind !== "idealo" ? c.store : win.store); // nombre editorial
      byKey.set(k, win);
    }
    const rows = [...byKey.values()].sort(cmp);
    rows.forEach((r, i) => { r.best = i === 0 && r.eur != null; r.small = r.kind === "idealo" && !isMajorShop(r.store); });
    return rows;
  }

  function storeCount(d) { return storeRows(d, null).length; }

  function matchesFacets(d, selected, skipKey) {
    if (!selected) return true;
    const f = d.facets || {};
    for (const k of Object.keys(selected)) {
      if (k !== skipKey && f[k] !== selected[k]) return false;
    }
    return true;
  }

  /**
   * Conteos para los chips de filtro de una sección. filters = [{key,label}], selected = {clave: valor},
   * universe = ofertas que definen qué valores existen (por defecto items). Para cada filtro el conteo ignora su
   * propia selección (así se ve cuánto daría cada alternativa) pero respeta la de los demás filtros.
   * Los filtros con menos de 2 valores distintos en el universo se omiten. Orden: nº desc, luego alfabético.
   */
  function facetCounts(items, filters, selected, universe) {
    const uni = universe || items, out = [];
    for (const f of filters || []) {
      const seen = new Set();
      for (const d of uni) { const v = (d.facets || {})[f.key]; if (v != null && v !== "") seen.add(v); }
      if (seen.size < 2) continue;
      const counts = new Map([...seen].map((v) => [v, 0]));
      for (const d of items) {
        const v = (d.facets || {})[f.key];
        if (counts.has(v) && matchesFacets(d, selected, f.key)) counts.set(v, counts.get(v) + 1);
      }
      const values = [...counts].map(([value, count]) => ({ value, count }))
        .sort((a, b) => (b.count - a.count) || a.value.localeCompare(b.value, "es"));
      out.push({ key: f.key, label: f.label, values });
    }
    return out;
  }

  const SEC_RE = /^[a-z0-9][a-z0-9_-]*$/, KEY_RE = /^[a-z][a-z0-9_]*$/;

  /** {sec:{k:v}} → «sec.k:valor~sec.k2:valor2» (valores con encodeURIComponent y «~» escapado). */
  function formatFacets(f) {
    const parts = [];
    for (const sec of Object.keys(f || {})) {
      for (const k of Object.keys(f[sec] || {})) {
        parts.push(sec + "." + k + ":" + encodeURIComponent(f[sec][k]).replace(/~/g, "%7E"));
      }
    }
    return parts.join("~");
  }

  /** Inverso tolerante de formatFacets: ignora cualquier trozo mal formado. */
  function parseFacets(s) {
    const out = {};
    if (typeof s !== "string" || !s) return out;
    for (const part of s.split("~")) {
      const m = /^([^.:~]+)\.([^.:~]+):(.+)$/.exec(part);
      if (!m || !SEC_RE.test(m[1]) || !KEY_RE.test(m[2])) continue;
      let v;
      try { v = decodeURIComponent(m[3]); } catch (e) { continue; }
      if (!v || v.length > 64) continue;
      if (!Object.prototype.hasOwnProperty.call(out, m[1])) out[m[1]] = {};
      out[m[1]][m[2]] = v;
    }
    return out;
  }

  /** Quita de una selección lo que ya no existe (sección, filtro o valor), p. ej. un enlace antiguo. */
  function pruneFacets(f, sections, offers) {
    const out = {};
    for (const s of sections || []) {
      const sel = f && Object.prototype.hasOwnProperty.call(f, s.id) ? f[s.id] : null;
      if (!sel) continue;
      for (const flt of s.filters || []) {
        const v = Object.prototype.hasOwnProperty.call(sel, flt.key) ? sel[flt.key] : null;
        if (v != null && offers.some((d) => d.section === s.id && (d.facets || {})[flt.key] === v)) {
          (out[s.id] = out[s.id] || {})[flt.key] = v;
        }
      }
    }
    return out;
  }

  /**
   * Filtra y ordena. state: {sec, q, verdict, sort, max (null = sin límite), real, facets}.
   * facets = {sección: {clave: valor}}: cada selección solo afecta a las ofertas de su sección.
   * Devuelve las ofertas ordenadas dentro de su sección (el orden de secciones lo decide quien pinta).
   */
  function query(offers, state, ctx) {
    const today = ctx.today, fx = ctx.fx || {}, titles = ctx.sectionTitles || {};
    const allowed = VERDICT_GROUPS[state.verdict || "all"];
    if (!allowed) throw new Error("Grupo de veredicto desconocido: " + state.verdict);
    const ts = terms(state.q), sel = state.facets;
    const out = offers.filter((d) => {
      if (state.sec && state.sec !== "all" && d.section !== state.sec) return false;
      if (!allowed.includes(d.verdict)) return false;
      if (ts.length && !matchesAll(haystack(d, titles[d.section]), ts)) return false;
      if (state.max != null) { const p = priceEur(d, fx); if (p != null && p > state.max) return false; }
      if (state.real && !d.below_annual_low) return false;
      if (!matchesFacets(d, sel && sel[d.section])) return false;
      return true;
    });
    const sort = state.sort || "rec";
    sortKey(sort, offers[0] || { rank: 0 }, today, fx); // valida el orden aunque no haya resultados
    return out
      .map((d) => ({ d, k: sortKey(sort, d, today, fx) }))
      .sort((a, b) => (a.k - b.k) || (a.d.rank - b.d.rank))
      .map((x) => x.d);
  }

  return { isMajorShop, storeKey, storeRows, storeCount, facetCounts, formatFacets, parseFacets, pruneFacets, normalize, terms, haystack, matchesAll, priceEur, daysLeft, query, VERDICT_GROUPS };
});
