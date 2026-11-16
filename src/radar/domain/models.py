"""Entidades del dominio. Sin dependencias de frameworks ni de E/S."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class Verdict(str, Enum):
    """Veredicto editorial sobre una oferta."""

    BUY = "top"
    GOOD = "ok"
    SKIP = "pasa"
    AVOID = "no"

    @property
    def label(self) -> str:
        return {
            Verdict.BUY: "Comprar",
            Verdict.GOOD: "Buena opción",
            Verdict.SKIP: "Pasa",
            Verdict.AVOID: "No comprar",
        }[self]

    @property
    def is_recommended(self) -> bool:
        return self in (Verdict.BUY, Verdict.GOOD)


@dataclass(frozen=True)
class Source:
    title: str
    url: str


@dataclass(frozen=True)
class SectionFilter:
    """Un filtro que la sección ofrece (p. ej. «marca»); cada oferta aporta su valor en `Offer.facets`."""

    key: str
    label: str


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    intro: str
    filters: tuple[SectionFilter, ...] = ()


@dataclass(frozen=True)
class TrackingSpec:
    """Dónde se sigue el precio real de una oferta (p. ej. su ficha en idealo) y cómo reconocer el producto exacto."""

    source: str
    product_id: str
    url: str
    include_regex: str = ""
    exclude_regex: str = ""


@dataclass(frozen=True)
class StoreOption:
    """Otra tienda donde se vende el mismo producto, verificada a mano (dato editorial)."""

    store: str
    url: str
    price: float | None = None
    currency: str = "€"
    checked_on: date | None = None
    note: str = ""


@dataclass(frozen=True)
class ShopPrice:
    """Precio total de una tienda leído de un comparador."""

    shop: str
    price: float


@dataclass(frozen=True)
class Offer:
    id: str
    section: str
    name: str
    store: str
    currency: str
    verdict: Verdict
    rank: int
    link: str
    price: float | None = None
    price_text: str | None = None
    reference_price: float | None = None
    reference_label: str = "precio habitual"
    annual_low: float | None = None
    annual_low_note: str = ""
    discount_override: int | None = None
    ends_on: date | None = None
    tags: tuple[str, ...] = ()
    highlights: tuple[str, ...] = ()
    note: str = ""
    info: str = ""
    illustration: str = "generic"
    image_query: str = ""
    image_url: str = ""
    sources: tuple[Source, ...] = field(default_factory=tuple)
    tracking: TrackingSpec | None = None
    options: tuple[StoreOption, ...] = ()
    checked_on: date | None = None  # última comprobación manual del precio principal
    facets: tuple[tuple[str, str], ...] = ()  # (clave de filtro, valor), inmutable

    def searchable_text(self) -> str:
        return " ".join((self.name, self.store, self.note, self.info, *self.tags, *self.highlights,
                         *(op.store for op in self.options),
                         *(v for _, v in self.facets)))


@dataclass(frozen=True)
class SourceQuote:
    """Mejor oferta válida que una fuente de precios devuelve para un producto."""

    price: float
    shop: str
    title: str
    url: str
    offers_seen: int
    offers_valid: int
    shops: tuple[ShopPrice, ...] = ()


@dataclass(frozen=True)
class PriceObservation:
    """Un precio real leído de una fuente externa en un momento dado. El histórico solo crece."""

    offer_id: str
    at: datetime
    price: float
    currency: str
    shop: str
    source: str
    url: str
    offers_seen: int = 0
    shops: tuple[ShopPrice, ...] = ()


@dataclass(frozen=True)
class MarketQuote:
    per_tb: float
    total: float
    tb: float
    name: str


@dataclass(frozen=True)
class Market:
    locale: str
    name: str
    code: str
    eu: bool
    currency: str
    hdd: MarketQuote
    ssd: MarketQuote | None
