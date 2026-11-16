"""Repositorio de solo lectura sobre data/seed.json."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from radar.domain.models import Group, Market, MarketQuote, Offer, Section, SectionFilter, Source, StoreOption, TrackingSpec, Verdict


class SeedError(ValueError):
    pass


class JsonSeedRepository:
    def __init__(self, path: str | Path) -> None:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        self._checked_on = date.fromisoformat(raw["checked_on"])
        self._fx: dict[str, float] = dict(raw["fx_to_eur"])
        self._sections = tuple(self._section(s) for s in raw["sections"])
        self._groups = self._parse_groups(raw.get("groups"), self._sections)
        sections = {s.id: s for s in self._sections}
        self._offers = tuple(self._offer(o, sections) for o in raw["offers"])
        ids = [o.id for o in self._offers]
        if len(ids) != len(set(ids)):
            raise SeedError("Hay ids de oferta duplicados")
        self._markets = tuple(self._market(m) for m in raw["markets"])

    def sections(self): return self._sections
    def offers(self): return self._offers
    def markets(self): return self._markets
    def fx_to_eur(self) -> Mapping[str, float]: return self._fx
    def checked_on(self) -> date: return self._checked_on
    def groups(self) -> tuple[Group, ...]: return self._groups

    _GROUP_ID = re.compile(r"[a-z][a-z0-9-]*")

    @classmethod
    def _parse_groups(cls, raw: Any, sections: tuple[Section, ...]) -> tuple[Group, ...]:
        if raw is None:
            stray = [s.id for s in sections if s.group is not None]
            if stray:
                raise SeedError(f"{stray[0]}: grupo desconocido (el seed no declara groups)")
            return ()
        if not isinstance(raw, list):
            raise SeedError("groups debe ser una lista")
        out: list[Group] = []
        for g in raw:
            gid, title = g.get("id"), g.get("title")
            if not isinstance(gid, str) or not cls._GROUP_ID.fullmatch(gid):
                raise SeedError(f"id de grupo no válido: {gid!r}")
            if any(x.id == gid for x in out):
                raise SeedError(f"grupo duplicado: {gid}")
            if not isinstance(title, str) or not title.strip() or any(ord(c) < 32 for c in title):
                raise SeedError(f"{gid}: título de grupo vacío o no válido")
            out.append(Group(id=gid, title=title.strip()))
        ids = {g.id for g in out}
        for s in sections:
            if s.group is None:
                raise SeedError(f"{s.id}: sección sin grupo")
            if s.group not in ids:
                raise SeedError(f"{s.id}: grupo desconocido {s.group}")
        empty = [g.id for g in out if not any(s.group == g.id for s in sections)]
        if empty:
            raise SeedError(f"{empty[0]}: grupo sin secciones")
        return tuple(out)

    MAX_FILTERS = 3
    MAX_FACET_LEN = 32
    _FILTER_KEY = re.compile(r"[a-z][a-z0-9_]*")

    @classmethod
    def _section(cls, s: Mapping[str, Any]) -> Section:
        extra = set(s) - {"id", "title", "intro", "filters", "group"}
        if extra:
            raise SeedError(f"{s.get('id')}: campos de sección desconocidos {sorted(extra)}")
        sid = s["id"]
        raw = s.get("filters")
        if raw is None:
            raw = []
        if not isinstance(raw, list):
            raise SeedError(f"{sid}: filters debe ser una lista")
        if len(raw) > cls.MAX_FILTERS:
            raise SeedError(f"{sid}: máximo {cls.MAX_FILTERS} filters")
        out: list[SectionFilter] = []
        for i, f in enumerate(raw):
            where = f"{sid}: filters[{i}]"
            if not isinstance(f, Mapping):
                raise SeedError(f"{where} debe ser un objeto")
            key, label = f.get("key"), f.get("label")
            if not isinstance(key, str) or not cls._FILTER_KEY.fullmatch(key):
                raise SeedError(f"{where}.key debe cumplir [a-z][a-z0-9_]*")
            if not isinstance(label, str) or not label.strip() or any(ord(c) < 32 for c in label):
                raise SeedError(f"{where}.label vacío o con caracteres de control")
            if any(key == x.key for x in out):
                raise SeedError(f"{where}: clave duplicada {key}")
            out.append(SectionFilter(key=key, label=label.strip()))
        group = s.get("group")
        if group is not None and not isinstance(group, str):
            raise SeedError(f"{sid}: group debe ser texto")
        return Section(id=sid, title=s["title"], intro=s["intro"], filters=tuple(out), group=group)

    @classmethod
    def _facets(cls, o: Mapping[str, Any], section: Section) -> tuple[tuple[str, str], ...]:
        raw = o.get("facets")
        if raw is None:
            return ()
        oid = o["id"]
        if not isinstance(raw, Mapping):
            raise SeedError(f"{oid}: facets debe ser un objeto")
        allowed = {f.key for f in section.filters}
        out = []
        for k, v in raw.items():
            if k not in allowed:
                raise SeedError(f"{oid}: facet «{k}» no está en los filters de la sección {section.id}")
            if not isinstance(v, str) or not v.strip():
                raise SeedError(f"{oid}: facets.{k} debe ser texto no vacío")
            if len(v.strip()) > cls.MAX_FACET_LEN:
                raise SeedError(f"{oid}: facets.{k} supera {cls.MAX_FACET_LEN} caracteres")
            if any(ord(c) < 32 or ord(c) == 127 for c in v):
                raise SeedError(f"{oid}: facets.{k} contiene caracteres de control")
            out.append((k, v.strip()))
        return tuple(out)

    def _offer(self, o: Mapping[str, Any], sections: Mapping[str, Section]) -> Offer:
        if o["section"] not in sections:
            raise SeedError(f"{o['id']}: sección desconocida {o['section']}")
        if o["currency"] not in self._fx:
            raise SeedError(f"{o['id']}: divisa sin tipo de cambio {o['currency']}")
        return Offer(
            id=o["id"], section=o["section"], name=o["name"], store=o["store"], currency=o["currency"],
            verdict=Verdict(o["verdict"]), rank=int(o["rank"]), link=o["link"],
            price=o.get("price"), price_text=o.get("price_text"),
            reference_price=o.get("reference_price"), reference_label=o.get("reference_label") or "precio habitual",
            annual_low=o.get("annual_low"), annual_low_note=o.get("annual_low_note") or "",
            discount_override=o.get("discount_override"),
            ends_on=date.fromisoformat(o["ends_on"]) if o.get("ends_on") else None,
            tags=tuple(o.get("tags") or ()), highlights=tuple(o.get("highlights") or ()),
            note=o.get("note") or "", info=o.get("info") or "",
            illustration=o.get("illustration") or "generic", image_query=o.get("image_query") or "",
            image_url=o.get("image_url") or "",
            sources=tuple(Source(**s) for s in o.get("sources") or ()),
            tracking=self._tracking(o),
            options=self._options(o),
            checked_on=self._date(o, "checked_on"),
            facets=self._facets(o, sections[o["section"]]),
        )

    @staticmethod
    def _date(o: Mapping[str, Any], key: str) -> date | None:
        v = o.get(key)
        if v is None:
            return None
        try:
            return date.fromisoformat(v)
        except (TypeError, ValueError) as exc:
            raise SeedError(f"{o['id']}: {key} debe ser una fecha ISO") from exc

    MAX_OPTIONS = 8

    def _options(self, o: Mapping[str, Any]) -> tuple[StoreOption, ...]:
        raw = o.get("options")
        if raw is None:
            return ()
        oid = o["id"]
        if not isinstance(raw, list):
            raise SeedError(f"{oid}: options debe ser una lista")
        if len(raw) > self.MAX_OPTIONS:
            raise SeedError(f"{oid}: máximo {self.MAX_OPTIONS} options")
        out = []
        for i, x in enumerate(raw):
            where = f"{oid}: options[{i}]"
            if not isinstance(x, Mapping):
                raise SeedError(f"{where} debe ser un objeto")
            store, url, note = x.get("store"), x.get("url"), x.get("note") or ""
            if not isinstance(store, str) or not store.strip():
                raise SeedError(f"{where}.store vacío")
            if not isinstance(url, str) or not url.startswith("https://"):
                raise SeedError(f"{where}.url debe ser https")
            price = x.get("price")
            if price is not None and (isinstance(price, bool) or not isinstance(price, (int, float))):
                raise SeedError(f"{where}.price debe ser número o null")
            currency = x.get("currency") or "€"
            if currency not in self._fx:
                raise SeedError(f"{where}: divisa sin tipo de cambio {currency}")
            checked = x.get("checked_on")
            try:
                checked_on = None if checked is None else date.fromisoformat(checked)
            except (TypeError, ValueError) as exc:
                raise SeedError(f"{where}.checked_on debe ser una fecha ISO") from exc
            if not isinstance(note, str):
                raise SeedError(f"{where}.note debe ser texto")
            if any(ord(c) < 32 for c in store + url + note):
                raise SeedError(f"{where} contiene caracteres de control")
            out.append(StoreOption(store=store.strip(), url=url, price=None if price is None else float(price),
                                   currency=currency, checked_on=checked_on, note=note))
        return tuple(out)

    @staticmethod
    def _tracking(o: Mapping[str, Any]) -> TrackingSpec | None:
        t = o.get("tracking")
        if not t:
            return None
        if not str(t.get("url", "")).startswith("https://"):
            raise SeedError(f"{o['id']}: tracking.url debe ser https")
        for key in ("include_regex", "exclude_regex"):
            if any(ord(c) < 32 for c in t.get(key) or ""):
                raise SeedError(f"{o['id']}: {key} contiene caracteres de control (¿\\b mal escapado?)")
            try:
                re.compile(t.get(key) or "")
            except re.error as exc:
                raise SeedError(f"{o['id']}: {key} inválida: {exc}") from exc
        return TrackingSpec(source=t["source"], product_id=str(t["product_id"]), url=t["url"],
                            include_regex=t.get("include_regex") or "", exclude_regex=t.get("exclude_regex") or "")

    @staticmethod
    def _market(m: Mapping[str, Any]) -> Market:
        return Market(
            locale=m["locale"], name=m["name"], code=m["code"], eu=bool(m["eu"]), currency=m["currency"],
            hdd=MarketQuote(**m["hdd"]), ssd=MarketQuote(**m["ssd"]) if m.get("ssd") else None,
        )
