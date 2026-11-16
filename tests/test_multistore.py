"""Multi-tienda: opciones editoriales del seed + tiendas leídas de idealo."""
import gzip
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from radar.adapters.idealo import IdealoOffer, IdealoPage, IdealoPriceSource, best_quote, parse_page
from radar.adapters.json_repository import JsonSeedRepository, SeedError
from radar.adapters.jsonl_history import JsonlPriceHistory
from radar.application.refresh import RefreshJob
from radar.application.services import CatalogService
from radar.domain.models import PriceObservation, ShopPrice, SourceQuote, StoreOption, TrackingSpec
from radar.domain.text import store_key

from .conftest import SEED, FakeRepo, make_offer

FIXTURE = Path(__file__).parent / "fixtures" / "idealo_matrix10.html.gz"
URL = "https://www.idealo.es/precios/207829835/dreame-matrix-10-ultra.html"
SPEC = TrackingSpec("idealo", "207829835", URL, include_regex=r"matrix\s?10\s*ultra")
NOW = datetime(2026, 11, 15, 17, 0, tzinfo=timezone.utc)


def opt(**kw):
    base = dict(store="PcComponentes", url="https://www.pccomponentes.com/x", price=619.0, currency="€",
                checked_on=date(2026, 11, 15), note="envío gratis")
    base.update(kw)
    return StoreOption(**base)


# ---------- dominio ----------

def test_searchable_text_includes_option_stores():
    o = make_offer(options=(opt(store="Coolmod"),))
    assert "coolmod" in o.searchable_text().lower()
    assert make_offer().options == ()


def test_store_key_normalizes_names():
    assert store_key("www.PcComponentes.com") == store_key("PcComponentes") == "pccomponentes"
    assert store_key("carrefour.es") == store_key("Carrefour")
    assert store_key("El Corte Inglés") == store_key("elcorteingles.es")
    assert store_key("Dreame ES (tienda oficial)") == "dreame"


# ---------- seed ----------

def _write(tmp_path, options, idx=0):
    raw = json.loads(SEED.read_text(encoding="utf-8"))
    raw["offers"][idx]["options"] = options
    p = tmp_path / "seed.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    return p


GOOD = {"store": "PcComponentes", "price": 619.0, "currency": "€", "url": "https://www.pccomponentes.com/x",
        "checked_on": "2026-11-15", "note": "envío gratis"}


def test_seed_parses_options(tmp_path):
    repo = JsonSeedRepository(_write(tmp_path, [GOOD, {**GOOD, "store": "Coolmod", "price": None, "checked_on": None}]))
    o = repo.offers()[0]
    assert o.options[0] == StoreOption("PcComponentes", "https://www.pccomponentes.com/x", 619.0, "€",
                                       date(2026, 11, 15), "envío gratis")
    assert o.options[1].price is None and o.options[1].checked_on is None


def test_seed_without_options_still_loads(seed_repo):
    assert all(isinstance(o.options, tuple) for o in seed_repo.offers())


@pytest.mark.parametrize("bad", [
    {"url": "http://x.es/p"}, {"url": ""}, {"store": ""}, {"store": "  "}, {"price": "619"}, {"price": True},
    {"checked_on": "15/11/2026"}, {"checked_on": 20261115}, {"currency": "¥"}, {"note": "a\x07b"},
])
def test_seed_rejects_bad_option(tmp_path, bad):
    with pytest.raises(SeedError):
        JsonSeedRepository(_write(tmp_path, [{**GOOD, **bad}]))


def test_seed_rejects_more_than_8_options_and_non_list(tmp_path):
    many = [{**GOOD, "store": f"T{i}"} for i in range(9)]
    with pytest.raises(SeedError):
        JsonSeedRepository(_write(tmp_path, many))
    JsonSeedRepository(_write(tmp_path, many[:8]))
    with pytest.raises(SeedError):
        JsonSeedRepository(_write(tmp_path, "nope"))


# ---------- idealo ----------

def page():
    return parse_page(gzip.open(FIXTURE, "rt", encoding="utf-8").read())


def test_best_quote_collects_valid_shops_sorted():
    q = best_quote(page(), SPEC, URL)
    assert q.shops == (ShopPrice("carrefour.es", 1221.97), ShopPrice("electronicabarata.com", 1640.59))
    assert q.shop == q.shops[0].shop and q.price == q.shops[0].price


def _pg(*offers):
    return IdealoPage(tuple(offers), None, None)


def test_shops_keep_cheapest_per_shop_and_cap_at_six():
    offers = [IdealoOffer("Robot X", 100 + i, f"tienda{i}.es", None, False) for i in range(8)]
    offers += [IdealoOffer("Robot X", 90, "Tienda3.es", None, False), IdealoOffer("Robot X", 500, "www.tienda0.es", None, False)]
    q = best_quote(_pg(*offers), TrackingSpec("idealo", "1", URL, include_regex="robot x"), URL)
    assert len(q.shops) == 6
    assert q.shops[0] == ShopPrice("Tienda3.es", 90)
    assert [s.price for s in q.shops] == sorted(s.price for s in q.shops)
    assert len({store_key(s.shop) for s in q.shops}) == 6
    assert q.offers_valid == 10


def test_shops_exclude_invalid_offers():
    q = best_quote(_pg(IdealoOffer("Robot X reacondicionado", 50, "a.es", None, False),
                       IdealoOffer("Robot X", 70, "b.es", None, False)),
                   TrackingSpec("idealo", "1", URL, include_regex="robot x"), URL)
    assert q.shops == (ShopPrice("b.es", 70),)


# ---------- histórico ----------

def _obs(shops=()):
    return PriceObservation("m10", NOW, 1221.97, "€", "carrefour.es", "idealo", URL, 7, shops)


def test_jsonl_roundtrip_with_shops(tmp_path):
    p = tmp_path / "o.jsonl"
    JsonlPriceHistory(p).record(_obs((ShopPrice("carrefour.es", 1221.97), ShopPrice("x.es", 1300.0))))
    line = json.loads(p.read_text().splitlines()[0])
    assert line["shops"] == [{"shop": "carrefour.es", "price": 1221.97}, {"shop": "x.es", "price": 1300.0}]
    got = JsonlPriceHistory(p).observations("m10")[0]
    assert got.shops == (ShopPrice("carrefour.es", 1221.97), ShopPrice("x.es", 1300.0))


def test_jsonl_reads_legacy_lines_without_shops(tmp_path):
    p = tmp_path / "o.jsonl"
    p.write_text(json.dumps({"offer_id": "m10", "at": "2026-11-15T17:00:00+00:00", "price": 10.0, "currency": "€",
                             "shop": "s", "source": "idealo", "url": URL, "offers_seen": 3}) + "\n")
    got = JsonlPriceHistory(p).observations("m10")
    assert len(got) == 1 and got[0].shops == ()


def test_jsonl_malformed_shops_ignores_only_that_line(tmp_path):
    p = tmp_path / "o.jsonl"
    base = {"offer_id": "m10", "at": "2026-11-15T17:00:00+00:00", "price": 10.0, "currency": "€",
            "shop": "s", "source": "idealo", "url": URL}
    p.write_text(json.dumps({**base, "shops": [{"shop": "a"}]}) + "\n" + json.dumps(base) + "\n")
    assert len(JsonlPriceHistory(p).observations("m10")) == 1


def test_refresh_records_shops():
    class Hist:
        rows = []
        def record(self, o): self.rows.append(o)
        def observations(self, i): return []

    class Src:
        def lookup(self, spec):
            return SourceQuote(99.0, "a", "t", "https://i/1", 5, 2, (ShopPrice("a", 99.0), ShopPrice("b", 120.0)))

    class N:
        def now(self): return NOW

    h = Hist()
    o = make_offer(id="a", tracking=TrackingSpec("idealo", "1", "https://i/1"))
    RefreshJob(FakeRepo([o]), Src(), h, N()).run()
    assert h.rows[0].shops == (ShopPrice("a", 99.0), ShopPrice("b", 120.0))


# ---------- payload ----------

class Hist:
    def __init__(self, obs): self._o = obs
    def observations(self, offer_id): return [o for o in self._o if o.offer_id == offer_id]


def test_payload_options_live_shops_and_store_count(clock):
    o = make_offer(id="m10", store="Dreame ES (tienda oficial)", price=599, tracking=TrackingSpec("idealo", "1", URL),
                   options=(opt(), opt(store="Carrefour", price=None, checked_on=None)))
    hist = Hist([_obs((ShopPrice("carrefour.es", 650.0), ShopPrice("www.pccomponentes.com", 640.0),
                       ShopPrice("Fnac", 660.0)))])
    d = CatalogService(FakeRepo([o]), clock, hist).payload()["offers"][0]
    assert d["options"][0] == {"store": "PcComponentes", "url": "https://www.pccomponentes.com/x", "price": 619.0,
                               "currency": "€", "checked_on": "2026-11-15", "note": "envío gratis"}
    assert d["options"][1]["checked_on"] is None
    assert d["live"]["shops"] == [{"shop": "carrefour.es", "price": 650.0},
                                  {"shop": "www.pccomponentes.com", "price": 640.0}, {"shop": "Fnac", "price": 660.0}]
    # dreame, pccomponentes, carrefour, fnac
    assert d["stores"] == 4
    json.dumps(d)  # serializable


def test_payload_without_options_or_live(clock):
    d = CatalogService(FakeRepo([make_offer()]), clock).payload()["offers"][0]
    assert d["options"] == [] and d["stores"] == 1 and d["live"] is None


def test_payload_live_without_shops_legacy(clock):
    o = make_offer(id="m10", tracking=TrackingSpec("idealo", "1", URL))
    d = CatalogService(FakeRepo([o]), clock, Hist([_obs()])).payload()["offers"][0]
    assert d["live"]["shops"] == [] and d["stores"] == 1


# ---------- revisión diaria: fecha de comprobación por oferta ----------

def _write_offer(tmp_path, **fields):
    raw = json.loads(SEED.read_text(encoding="utf-8"))
    raw["offers"][0].update(fields)
    p = tmp_path / "seed.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    return p


def test_offer_checked_on_parsed_and_optional(tmp_path, seed_repo):
    assert JsonSeedRepository(_write_offer(tmp_path, checked_on="2026-11-16")).offers()[0].checked_on == date(2026, 11, 16)
    assert seed_repo.offers()[0].checked_on is None or isinstance(seed_repo.offers()[0].checked_on, date)
    with pytest.raises(SeedError):
        JsonSeedRepository(_write_offer(tmp_path, checked_on="16/11/2026"))


def test_payload_exposes_offer_checked_on(clock):
    svc = CatalogService(FakeRepo([make_offer(checked_on=date(2026, 11, 16))]), clock)
    assert svc.payload()["offers"][0]["checked_on"] == "2026-11-16"
    svc = CatalogService(FakeRepo([make_offer()]), clock)
    assert svc.payload()["offers"][0]["checked_on"] is None
