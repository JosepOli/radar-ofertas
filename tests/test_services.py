from datetime import date

import pytest

from radar.application.services import CatalogService, OfferNotFound, PhotoService
from radar.domain.catalog import OfferQuery
from radar.domain.models import Market, MarketQuote, Section, Verdict

from .conftest import FakeRepo, make_offer

OFFER = make_offer(id="m10", name="Matrix10", price=649, reference_price=1299, annual_low=735,
                   verdict=Verdict.BUY, ends_on=date(2026, 11, 30), image_query="Dreame Matrix10")


class MemCache:
    def __init__(self): self.store = {}
    def get(self, k): return self.store.get(k)
    def put(self, k, v): self.store[k] = v


class StubProvider:
    def __init__(self, data=b"\xff\xd8\xffJPEG", boom=False):
        self.calls, self.data, self.boom = [], data, boom

    def find(self, q):
        self.calls.append(q)
        if self.boom:
            raise RuntimeError("red caída")
        return self.data


def test_view_exposes_derived_fields(clock):
    svc = CatalogService(FakeRepo([OFFER]), clock)
    v = svc.get("m10")
    assert v["discount_pct"] == 50
    assert v["vs_annual_low_pct"] == -12
    assert v["below_annual_low"] is True
    assert v["days_left"] == 15
    assert v["verdict"] == "top" and v["verdict_label"] == "Comprar"
    assert v["photo_url"] == "/img/m10"


def test_get_unknown_raises(clock):
    with pytest.raises(OfferNotFound):
        CatalogService(FakeRepo([]), clock).get("nope")


def test_sections_include_counts(clock):
    repo = FakeRepo([OFFER], sections=[Section("robots", "Robots", "intro"), Section("gpu", "GPU", "")])
    counts = {s["id"]: s["count"] for s in CatalogService(repo, clock).sections()}
    assert counts == {"robots": 1, "gpu": 0}


def test_markets_are_converted_to_eur(clock):
    m = Market("us", "EE. UU.", "US", False, "$", MarketQuote(37.43, 524, 14, "IronWolf"), None)
    row = CatalogService(FakeRepo([], markets=[m]), clock).markets()[0]
    assert row["hdd"]["per_tb_eur"] == pytest.approx(37.43 * 0.86)
    assert row["ssd"] is None
    assert row["diskprices_url"].endswith("locale=us")


def test_search_delegates_to_query(clock):
    res = CatalogService(FakeRepo([OFFER]), clock).search(OfferQuery(verdict_group="skip"))
    assert res == []


def test_photo_is_fetched_once_then_served_from_cache():
    cache, prov = MemCache(), StubProvider()
    svc = PhotoService(FakeRepo([OFFER]), cache, prov)
    assert svc.photo("m10") == b"\xff\xd8\xffJPEG"
    assert svc.photo("m10") == b"\xff\xd8\xffJPEG"
    assert prov.calls == ["Dreame Matrix10"]


def test_photo_provider_failure_returns_none_and_does_not_cache():
    cache = MemCache()
    svc = PhotoService(FakeRepo([OFFER]), cache, StubProvider(boom=True))
    assert svc.photo("m10") is None
    assert cache.store == {}


def test_photo_without_provider_only_uses_cache():
    cache = MemCache()
    cache.put("m10", b"cached")
    assert PhotoService(FakeRepo([OFFER]), cache, None).photo("m10") == b"cached"


def test_photo_unknown_offer_raises():
    with pytest.raises(OfferNotFound):
        PhotoService(FakeRepo([]), MemCache(), None).photo("nope")


def test_warm_all_reports_per_offer():
    assert PhotoService(FakeRepo([OFFER]), MemCache(), StubProvider()).warm_all() == {"m10": True}
