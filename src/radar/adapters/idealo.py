"""Fuente de precios: fichas de producto de idealo.es.

idealo bloquea los clientes HTTP simples (Akamai), así que el fetcher por defecto usa curl_cffi con huella de Chrome.
El fetcher se inyecta: las pruebas usan HTML real guardado en tests/fixtures.
"""
from __future__ import annotations

import html as html_lib
import re
import time
from dataclasses import dataclass
from typing import Callable

from radar.domain.text import store_key
from radar.domain.models import ShopPrice, SourceQuote, TrackingSpec

Fetch = Callable[[str], str]

ALWAYS_EXCLUDE = re.compile(r"reacondicionad|refurbished|\busad[oa]s?\b|segunda mano|b-stock|\bdemo\b|\bopen box\b", re.I)
BLOCKED_SHOPS = ("amazon us", "amazon.com", "amazon uk", "amazon.co.uk", "aliexpress", "joom", "wish", "ebay",
                 "shumee", "banggood", "temu", "back market", "backmarket", "rebuy", "swappie", "refurbed",
                 "certideal")
TRUSTED_PLATFORM_MERCHANTS = ("amazon", "pccomponentes", "carrefour", "fnac", "worten", "mediamarkt",
                              "el corte ingl", "elcorteingles", "coolmod")
# Tiendas oficiales de marca que venden dentro de un marketplace («Roborock official», «… OFFICIEL», «GMKtec直営店»).
OFFICIAL_MERCHANT = re.compile(r"\bofficial\b|\bofficiel\b|\boficial\b|直営", re.I)


@dataclass(frozen=True)
class IdealoOffer:
    title: str
    total: float
    shop: str
    merchant: str | None
    marketplace: bool


@dataclass(frozen=True)
class IdealoPage:
    offers: tuple[IdealoOffer, ...]
    from_price: float | None
    image: str | None


def _clean(s: str | None) -> str:
    s = html_lib.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s.replace("\xad", "")).strip()


def _eur(s: str | None) -> float | None:
    return float(s.replace(".", "").replace(",", ".")) if s else None


def parse_page(page_html: str) -> IdealoPage:
    offers = []
    for it in re.split(r'<li\s+class="productOffers-listItem\b', page_html)[1:]:
        title = re.search(r"productOffers-listItemTitleInner[^>]*>(.*?)</", it, re.S)
        total = re.search(r'productOffers-listItemOfferShippingDetails"?[^>]*>\s*([\d.]+,\d{2})\s*€', it, re.S)
        price = re.search(r"productOffers-listItemOfferPrice[^>]*>.*?([\d.]+,\d{2})\s*€", it, re.S)
        shop = re.search(r'productOffers-listItemOfferShopV2LogoImage"[^>]*?alt="([^"]+)"', it, re.S)
        merchant = re.search(r'MarketPlaceMerchantName">\s*<a[^>]*title="([^"]+)"', it, re.S)
        if not (title and (total or price) and shop):
            continue
        offers.append(IdealoOffer(
            title=_clean(title.group(1)),
            total=_eur(total.group(1)) if total else _eur(price.group(1)),
            shop=_clean(shop.group(1)).split(" - Tienda de ")[0].rstrip("/"),
            merchant=_clean(merchant.group(1)) if merchant else None,
            marketplace="productOffers-listItemOfferShopV2MarketPlace" in it,
        ))
    head = re.search(r"<title>(.*?)</title>", page_html, re.S)
    from_price = None
    if head and (m := re.search(r"desde\s+([\d.]+,\d{2})", _clean(head.group(1)))):
        from_price = _eur(m.group(1))
    img = re.search(r'og:image"\s+content="([^"]+)"', page_html)
    return IdealoPage(tuple(offers), from_price, img.group(1) if img else None)


def is_valid(o: IdealoOffer, spec: TrackingSpec) -> bool:
    if spec.include_regex and not re.search(spec.include_regex, o.title, re.I):
        return False
    if spec.exclude_regex and re.search(spec.exclude_regex, o.title, re.I):
        return False
    if ALWAYS_EXCLUDE.search(o.title):
        return False
    shop, merchant = o.shop.lower(), (o.merchant or "").lower()
    if any(b in shop or b in merchant for b in BLOCKED_SHOPS):
        return False
    if o.marketplace or o.merchant:  # vendedor de terceros: solo la propia plataforma o la tienda oficial de la marca
        return any(p in merchant for p in TRUSTED_PLATFORM_MERCHANTS) or bool(OFFICIAL_MERCHANT.search(merchant))
    return True


MAX_SHOPS = 6


def shop_prices(valid_sorted: list[IdealoOffer], limit: int = MAX_SHOPS) -> tuple[ShopPrice, ...]:
    """La oferta más barata de cada tienda distinta, de menor a mayor precio."""
    seen: set[str] = set()
    out: list[ShopPrice] = []
    for o in valid_sorted:
        key = store_key(o.shop)
        if key in seen:
            continue
        seen.add(key)
        out.append(ShopPrice(o.shop, o.total))
        if len(out) == limit:
            break
    return tuple(out)


def best_quote(page: IdealoPage, spec: TrackingSpec, url: str) -> SourceQuote | None:
    valid = sorted((o for o in page.offers if is_valid(o, spec)), key=lambda o: o.total)
    if not valid:
        return None
    best = valid[0]
    return SourceQuote(price=best.total, shop=best.shop, title=best.title, url=url,
                       offers_seen=len(page.offers), offers_valid=len(valid), shops=shop_prices(valid))


class IdealoPriceSource:
    def __init__(self, fetch: Fetch, delay_s: float = 3.0) -> None:
        self._fetch = fetch
        self._delay = delay_s
        self._last = 0.0

    def lookup(self, spec: TrackingSpec) -> SourceQuote | None:
        wait = self._delay - (time.monotonic() - self._last)
        if wait > 0 and self._last:
            time.sleep(wait)
        try:
            page = parse_page(self._fetch(spec.url))
        finally:
            self._last = time.monotonic()
        if not page.offers:
            raise RuntimeError("0 ofertas leídas (¿bloqueo o cambio de diseño de idealo?)")
        return best_quote(page, spec, spec.url)


def curl_cffi_fetcher(timeout: float = 30) -> Fetch:
    """Fetcher real. Import tardío: curl_cffi solo hace falta para refrescar precios."""
    from curl_cffi import requests as cr

    session = cr.Session(impersonate="chrome")

    def fetch(url: str) -> str:
        resp = session.get(url, timeout=timeout, headers={"Accept-Language": "es-ES,es;q=0.9"})
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        return resp.text

    return fetch
