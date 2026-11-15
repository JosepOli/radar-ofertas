"""Refresco de precios reales. Solo añade observaciones al histórico: nunca toca el seed ni los campos editoriales."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from radar.domain.models import PriceObservation

from .ports import Now, OfferRepository, PriceHistory, PriceSource

log = logging.getLogger(__name__)


@dataclass
class RefreshReport:
    tracked: int = 0
    ok: list[str] = field(default_factory=list)
    no_valid: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)

    @property
    def all_failed(self) -> bool:
        return self.tracked > 0 and len(self.failed) == self.tracked

    def summary(self) -> str:
        lines = [f"Seguidas {self.tracked}: {len(self.ok)} con precio, {len(self.no_valid)} sin oferta válida, "
                 f"{len(self.failed)} con error."]
        lines += [f"  error {k}: {v}" for k, v in self.failed.items()]
        lines += [f"  sin oferta válida: {k}" for k in self.no_valid]
        return "\n".join(lines)


class RefreshJob:
    def __init__(self, repo: OfferRepository, source: PriceSource, history: PriceHistory, clock: Now) -> None:
        self._repo = repo
        self._source = source
        self._history = history
        self._clock = clock

    def run(self, only: set[str] | None = None) -> RefreshReport:
        report = RefreshReport()
        for offer in self._repo.offers():
            if offer.tracking is None or (only and offer.id not in only):
                continue
            report.tracked += 1
            try:
                quote = self._source.lookup(offer.tracking)
            except Exception as exc:  # un fallo es «estado desconocido»: no se registra nada
                report.failed[offer.id] = f"{type(exc).__name__}: {exc}"[:200]
                log.warning("Refresco fallido %s: %s", offer.id, exc)
                continue
            if quote is None:
                report.no_valid.append(offer.id)
                continue
            self._history.record(PriceObservation(
                offer_id=offer.id, at=self._clock.now(), price=quote.price, currency="€",
                shop=quote.shop, source=offer.tracking.source, url=quote.url, offers_seen=quote.offers_seen,
                shops=quote.shops,
            ))
            report.ok.append(offer.id)
        return report
