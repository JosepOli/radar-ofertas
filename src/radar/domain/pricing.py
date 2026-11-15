"""Reglas de precio puras: descuentos, comparación con el mínimo anual, plazos y divisas."""
from __future__ import annotations

from datetime import date
from typing import Mapping


def discount_pct(price: float | None, reference: float | None) -> int | None:
    """Descuento en % frente al precio de referencia.

    Positivo = más barato que la referencia; negativo = más caro (subida).
    """
    if price is None or not reference:
        return None
    return round((1 - price / reference) * 100)


def vs_annual_low_pct(price: float | None, annual_low: float | None) -> int | None:
    """Diferencia en % frente al mínimo anual. Negativo = por debajo del mínimo."""
    if price is None or not annual_low:
        return None
    return round((price / annual_low - 1) * 100)


def is_below_annual_low(price: float | None, annual_low: float | None) -> bool:
    if price is None or not annual_low:
        return False
    return price < annual_low


def days_left(ends_on: date | None, today: date) -> int | None:
    """Días que quedan hasta el final de la oferta, incluido el último día."""
    if ends_on is None:
        return None
    return (ends_on - today).days


def to_eur(amount: float | None, currency: str, fx_to_eur: Mapping[str, float]) -> float | None:
    if amount is None:
        return None
    try:
        return amount * fx_to_eur[currency]
    except KeyError as exc:
        raise ValueError(f"Divisa sin tipo de cambio: {currency}") from exc
