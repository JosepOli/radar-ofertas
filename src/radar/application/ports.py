"""Puertos (interfaces) que la capa de aplicación necesita. Las implementaciones viven en adapters/."""
from __future__ import annotations

from datetime import date, datetime
from typing import Mapping, Protocol, Sequence

from radar.domain.models import Group, Market, Offer, PriceObservation, Section, SourceQuote, TrackingSpec


class OfferRepository(Protocol):
    def sections(self) -> Sequence[Section]: ...
    def groups(self) -> Sequence[Group]: ...
    def offers(self) -> Sequence[Offer]: ...
    def markets(self) -> Sequence[Market]: ...
    def fx_to_eur(self) -> Mapping[str, float]: ...
    def checked_on(self) -> date: ...


class ImageProvider(Protocol):
    """Busca una foto de producto en una fuente externa. Devuelve bytes JPEG/PNG/WebP o None."""

    def find(self, query: str) -> bytes | None: ...


class ImageCache(Protocol):
    def get(self, key: str) -> bytes | None: ...
    def put(self, key: str, data: bytes) -> None: ...


class PriceSource(Protocol):
    """Lee el mejor precio válido de un producto exacto. None = el producto existe pero no hay oferta válida.

    Debe lanzar una excepción si la fuente falla (red, bloqueo, cambio de diseño): un fallo nunca es «sin oferta».
    """

    def lookup(self, spec: TrackingSpec) -> SourceQuote | None: ...


class PriceHistory(Protocol):
    def record(self, obs: PriceObservation) -> None: ...
    def observations(self, offer_id: str) -> Sequence[PriceObservation]: ...


class Clock(Protocol):
    def today(self) -> date: ...


class Now(Protocol):
    def now(self) -> datetime: ...
