"""Histórico de precios en un fichero JSON Lines append-only (legible y versionable en Git)."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from radar.domain.models import PriceObservation

log = logging.getLogger(__name__)


class JsonlPriceHistory:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._cache: list[PriceObservation] | None = None

    def _load(self) -> list[PriceObservation]:
        if self._cache is None:
            rows: list[PriceObservation] = []
            if self._path.exists():
                for n, line in enumerate(self._path.read_text(encoding="utf-8").splitlines(), 1):
                    if not line.strip():
                        continue
                    try:
                        r = json.loads(line)
                        rows.append(PriceObservation(
                            offer_id=r["offer_id"], at=datetime.fromisoformat(r["at"]), price=float(r["price"]),
                            currency=r["currency"], shop=r["shop"], source=r["source"], url=r["url"],
                            offers_seen=int(r.get("offers_seen", 0)),
                        ))
                    except (ValueError, KeyError, TypeError):
                        log.warning("Línea %d del histórico ilegible; se ignora", n)
            self._cache = rows
        return self._cache

    def observations(self, offer_id: str) -> list[PriceObservation]:
        return [o for o in self._load() if o.offer_id == offer_id]

    def record(self, obs: PriceObservation) -> None:
        line = json.dumps({
            "offer_id": obs.offer_id, "at": obs.at.isoformat(timespec="seconds"), "price": obs.price,
            "currency": obs.currency, "shop": obs.shop, "source": obs.source, "url": obs.url,
            "offers_seen": obs.offers_seen,
        }, ensure_ascii=False)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
        self._load().append(obs)
