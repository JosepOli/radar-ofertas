"""Casos de uso. Dependen solo de puertos (inversión de dependencias)."""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from radar.domain.catalog import OfferQuery, effective_discount, run_query
from radar.domain.history import summarize
from radar.domain.models import Offer
from radar.domain.text import store_key
from radar.domain.pricing import days_left, is_below_annual_low, to_eur, vs_annual_low_pct

from .ports import Clock, ImageCache, ImageProvider, OfferRepository, PriceHistory

log = logging.getLogger(__name__)


class OfferNotFound(LookupError):
    pass


class CatalogService:
    def __init__(self, repo: OfferRepository, clock: Clock, history: PriceHistory | None = None) -> None:
        self._repo = repo
        self._clock = clock
        self._history = history

    def sections(self) -> list[dict[str, Any]]:
        offers = self._repo.offers()
        return [
            {**asdict(s), "count": sum(1 for o in offers if o.section == s.id)}
            for s in self._repo.sections()
        ]

    def search(self, query: OfferQuery) -> list[dict[str, Any]]:
        today = self._clock.today()
        found = run_query(self._repo.offers(), query, today, self._repo.fx_to_eur())
        return [self._view(o, today) for o in found]

    def get(self, offer_id: str) -> dict[str, Any]:
        for o in self._repo.offers():
            if o.id == offer_id:
                return self._view(o, self._clock.today())
        raise OfferNotFound(offer_id)

    def all(self) -> list[dict[str, Any]]:
        today = self._clock.today()
        return [self._view(o, today) for o in self._repo.offers()]

    def markets(self) -> list[dict[str, Any]]:
        fx = self._repo.fx_to_eur()
        rows = []
        for m in self._repo.markets():
            rows.append({
                "locale": m.locale, "name": m.name, "code": m.code, "eu": m.eu, "currency": m.currency,
                "hdd": {**asdict(m.hdd), "per_tb_eur": to_eur(m.hdd.per_tb, m.currency, fx)},
                "ssd": None if m.ssd is None else {**asdict(m.ssd), "per_tb_eur": to_eur(m.ssd.per_tb, m.currency, fx)},
                "diskprices_url": f"https://diskprices.com/?locale={m.locale}",
            })
        return rows

    def meta(self) -> dict[str, Any]:
        return {
            "checked_on": self._repo.checked_on().isoformat(),
            "today": self._clock.today().isoformat(),
            "generated_at": self._now().isoformat(timespec="minutes"),
            "fx_to_eur": dict(self._repo.fx_to_eur()),
        }

    def payload(self) -> dict[str, Any]:
        """Todo lo que necesita el frontend en un único documento (sitio estático o /data.json)."""
        return {"meta": self.meta(), "sections": self.sections(), "markets": self.markets(), "offers": self.all()}

    def _now(self) -> datetime:
        now = getattr(self._clock, "now", None)
        return now() if now else datetime.now(timezone.utc)

    def _live(self, o: Offer) -> dict[str, Any] | None:
        if self._history is None or o.tracking is None:
            return None
        s = summarize(self._history.observations(o.id), self._now())
        if s is None:
            return None
        offer_vs_market = None
        if o.price is not None and o.currency == s.latest.currency and s.latest.price:
            offer_vs_market = round((o.price / s.latest.price - 1) * 100)
        return {
            "price": s.latest.price,
            "currency": s.latest.currency,
            "shop": s.latest.shop,
            "at": s.latest.at.isoformat(timespec="minutes"),
            "url": s.latest.url,
            "source": s.latest.source,
            "offers_seen": s.latest.offers_seen,
            "lowest": s.lowest.price,
            "lowest_shop": s.lowest.shop,
            "lowest_at": s.lowest.at.isoformat(timespec="minutes"),
            "since": s.since.isoformat(),
            "count": s.count,
            "stale": s.is_stale,
            "offer_vs_market_pct": offer_vs_market,
            "shops": [{"shop": x.shop, "price": x.price} for x in s.latest.shops],
        }

    def _view(self, o: Offer, today) -> dict[str, Any]:
        d = asdict(o)
        d["verdict"] = o.verdict.value
        d["verdict_label"] = o.verdict.label
        d["ends_on"] = o.ends_on.isoformat() if o.ends_on else None
        d["checked_on"] = o.checked_on.isoformat() if o.checked_on else None
        d["discount_pct"] = effective_discount(o)
        d["vs_annual_low_pct"] = vs_annual_low_pct(o.price, o.annual_low)
        d["below_annual_low"] = is_below_annual_low(o.price, o.annual_low)
        d["days_left"] = days_left(o.ends_on, today)
        d["photo_url"] = f"/img/{o.id}"
        d["live"] = self._live(o)
        d["options"] = [{**asdict(op), "checked_on": op.checked_on.isoformat() if op.checked_on else None}
                        for op in o.options]
        d["stores"] = len({store_key(n) for n in (o.store, *(op.store for op in o.options),
                                                 *(x["shop"] for x in (d["live"] or {}).get("shops", ())))})
        d.pop("image_query", None)
        if o.tracking is not None:
            d["tracking"] = {"source": o.tracking.source, "url": o.tracking.url}
        return d


class PhotoService:
    """Devuelve la foto de una oferta: primero caché local; si falta, la busca y la guarda."""

    def __init__(self, repo: OfferRepository, cache: ImageCache, provider: ImageProvider | None) -> None:
        self._repo = repo
        self._cache = cache
        self._provider = provider

    def photo(self, offer_id: str) -> bytes | None:
        offer = next((o for o in self._repo.offers() if o.id == offer_id), None)
        if offer is None:
            raise OfferNotFound(offer_id)
        cached = self._cache.get(offer.id)
        if cached is not None:
            return cached
        if self._provider is None or not offer.image_query:
            return None
        try:
            data = self._provider.find(offer.image_query)
        except Exception:  # un proveedor externo nunca debe tumbar la API
            log.exception("Fallo buscando foto para %s", offer.id)
            return None
        if data:
            self._cache.put(offer.id, data)
        return data

    def warm_all(self) -> dict[str, bool]:
        """Precarga todas las fotos (para un cron o el arranque)."""
        return {o.id: self.photo(o.id) is not None for o in self._repo.offers()}
