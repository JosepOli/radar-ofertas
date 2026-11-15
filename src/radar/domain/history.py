"""Resumen del histórico de precios reales observados. Puro: recibe observaciones y la hora actual."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Sequence

from .models import PriceObservation

STALE_AFTER_HOURS = 36


@dataclass(frozen=True)
class HistorySummary:
    latest: PriceObservation
    lowest: PriceObservation
    since: date
    count: int
    age_hours: float

    @property
    def is_stale(self) -> bool:
        return self.age_hours > STALE_AFTER_HOURS


def summarize(observations: Sequence[PriceObservation], now: datetime) -> HistorySummary | None:
    if not observations:
        return None
    ordered = sorted(observations, key=lambda o: o.at)
    latest = ordered[-1]
    lowest = min(ordered, key=lambda o: o.price)  # min() conserva la primera en caso de empate
    return HistorySummary(
        latest=latest,
        lowest=lowest,
        since=ordered[0].at.date(),
        count=len(ordered),
        age_hours=(now - latest.at).total_seconds() / 3600,
    )
