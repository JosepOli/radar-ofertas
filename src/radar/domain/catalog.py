"""Consulta del catálogo: filtros y ordenaciones como estrategias intercambiables (abierto/cerrado)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Iterable, Mapping

from .models import Offer, Verdict
from .pricing import days_left, discount_pct, is_below_annual_low, vs_annual_low_pct
from .text import matches_all_terms

Predicate = Callable[[Offer], bool]
SortKey = Callable[[Offer], object]

EUR_ONLY: Mapping[str, float] = {"€": 1.0}

VERDICT_GROUPS: dict[str, frozenset[Verdict]] = {
    "all": frozenset(Verdict),
    "buy": frozenset({Verdict.BUY, Verdict.GOOD}),
    "top": frozenset({Verdict.BUY}),
    "skip": frozenset({Verdict.SKIP, Verdict.AVOID}),
}


@dataclass(frozen=True)
class OfferQuery:
    section: str | None = None
    text: str = ""
    verdict_group: str = "all"
    max_price: float | None = None
    only_below_annual_low: bool = False
    sort: str = "rec"


def effective_discount(offer: Offer) -> int | None:
    if offer.discount_override is not None:
        return offer.discount_override
    return discount_pct(offer.price, offer.reference_price)


def price_in_eur(offer: Offer, fx: Mapping[str, float]) -> float | None:
    if offer.price is None:
        return None
    return offer.price * fx.get(offer.currency, 1.0)


def build_predicates(query: OfferQuery, fx: Mapping[str, float] = EUR_ONLY) -> list[Predicate]:
    if query.verdict_group not in VERDICT_GROUPS:
        raise ValueError(f"Grupo de veredicto desconocido: {query.verdict_group}")
    preds: list[Predicate] = []
    if query.section:
        preds.append(lambda o: o.section == query.section)
    if query.text.strip():
        preds.append(lambda o: matches_all_terms(o.searchable_text(), query.text))
    allowed = VERDICT_GROUPS[query.verdict_group]
    preds.append(lambda o: o.verdict in allowed)
    if query.max_price is not None:
        preds.append(lambda o: (p := price_in_eur(o, fx)) is None or p <= query.max_price)
    if query.only_below_annual_low:
        preds.append(lambda o: is_below_annual_low(o.price, o.annual_low))
    return preds


def sorters(today: date, fx: Mapping[str, float] = EUR_ONLY) -> dict[str, SortKey]:
    big = 10**9
    return {
        "rec": lambda o: o.rank,
        "disc": lambda o: -(effective_discount(o) if effective_discount(o) is not None else -big),
        "low": lambda o: vs_annual_low_pct(o.price, o.annual_low) if o.annual_low and o.price is not None else big,
        "price": lambda o: p if (p := price_in_eur(o, fx)) is not None else big,
        "end": lambda o: d if (d := days_left(o.ends_on, today)) is not None else big,
    }


def run_query(offers: Iterable[Offer], query: OfferQuery, today: date,
              fx: Mapping[str, float] = EUR_ONLY) -> list[Offer]:
    keys = sorters(today, fx)
    if query.sort not in keys:
        raise ValueError(f"Orden desconocido: {query.sort}")
    preds = build_predicates(query, fx)
    result = [o for o in offers if all(p(o) for p in preds)]
    return sorted(result, key=lambda o: (o.section, keys[query.sort](o), o.rank))
