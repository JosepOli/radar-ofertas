"""Repositorio de solo lectura sobre data/seed.json."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from radar.domain.models import Market, MarketQuote, Offer, Section, Source, StoreOption, TrackingSpec, Verdict


class SeedError(ValueError):
    pass


class JsonSeedRepository:
    def __init__(self, path: str | Path) -> None:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        self._checked_on = date.fromisoformat(raw["checked_on"])
        self._fx: dict[str, float] = dict(raw["fx_to_eur"])
        self._sections = tuple(Section(**s) for s in raw["sections"])
        section_ids = {s.id for s in self._sections}
        self._offers = tuple(self._offer(o, section_ids) for o in raw["offers"])
        ids = [o.id for o in self._offers]
        if len(ids) != len(set(ids)):
            raise SeedError("Hay ids de oferta duplicados")
        self._markets = tuple(self._market(m) for m in raw["markets"])

    def sections(self): return self._sections
    def offers(self): return self._offers
    def markets(self): return self._markets
    def fx_to_eur(self) -> Mapping[str, float]: return self._fx
    def checked_on(self) -> date: return self._checked_on

    def _offer(self, o: Mapping[str, Any], section_ids: set[str]) -> Offer:
        if o["section"] not in section_ids:
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
