import gzip
from datetime import datetime, timezone
from pathlib import Path

import pytest

from radar.adapters.idealo import IdealoOffer, IdealoPriceSource, best_quote, is_valid, parse_page
from radar.adapters.jsonl_history import JsonlPriceHistory
from radar.application.refresh import RefreshJob
from radar.domain.models import PriceObservation, SourceQuote, TrackingSpec

from .conftest import FakeRepo, make_offer

FIXTURE = Path(__file__).parent / "fixtures" / "idealo_matrix10.html.gz"
URL = "https://www.idealo.es/precios/207829835/dreame-matrix-10-ultra.html"
SPEC = TrackingSpec("idealo", "207829835", URL, include_regex=r"matrix\s?10\s*ultra",
                    exclude_regex=r"reacondicionad|usad[oa]|segunda mano|b-stock")
NOW = datetime(2026, 11, 15, 17, 0, tzinfo=timezone.utc)


def page():
    return gzip.open(FIXTURE, "rt", encoding="utf-8").read()


# ---------- parser de idealo (HTML real guardado el 15/11/2026) ----------

def test_parse_page_reads_offers_headline_and_image():
    p = parse_page(page())
    assert len(p.offers) == 7
    assert p.from_price == 899.0
    assert p.image.startswith("https://cdn.idealo.com/") and p.image.endswith(".jpg")
    first = p.offers[0]
    assert first.total == 907.0 and first.shop == "kaufland.es" and first.marketplace


def test_best_quote_skips_third_party_marketplaces_and_picks_cheapest_valid():
    q = best_quote(parse_page(page()), SPEC, URL)
    assert q.shop == "carrefour.es" and q.price == 1221.97
    assert q.offers_seen == 7 and q.offers_valid == 2
    assert q.url == URL


def test_best_quote_respects_exclude_regex():
    spec = TrackingSpec("idealo", "1", URL, include_regex="matrix", exclude_regex="combinado|negro")
    q = best_quote(parse_page(page()), spec, URL)
    assert q.shop == "electronicabarata.com"


def test_best_quote_none_when_nothing_valid():
    spec = TrackingSpec("idealo", "1", URL, include_regex="no-existe")
    assert best_quote(parse_page(page()), spec, URL) is None


def test_marketplace_rules_official_brand_stores_yes_uk_imports_and_refurb_shops_no():
    spec = TrackingSpec("idealo", "1", URL, include_regex="qrevo")
    ok = [IdealoOffer("Roborock Qrevo 2 Pro", 299, "pccomponentes.com", "Roborock official", True),
          IdealoOffer("Roborock Qrevo 2 Pro", 299, "manomano.es", "ROBOROCK OFFICIEL", True),
          IdealoOffer("Qrevo mini PC", 1, "Amazon Marketplace (ES)", "GMKtec直営店", True),
          IdealoOffer("Roborock Qrevo", 300, "Amazon Marketplace (ES)", "Amazon", True),
          IdealoOffer("Roborock Qrevo", 300, "pccomponentes.com", "PcComponentes", True)]
    bad = [IdealoOffer("Roborock Qrevo", 250, "Amazon Marketplace (ES)", "Amazon UK", True),
           IdealoOffer("Roborock Qrevo", 250, "Back Market", None, False),
           IdealoOffer("Roborock Qrevo", 250, "kaufland.es", "EVELATUS", True),
           IdealoOffer("Roborock Qrevo (T)", 250, "shop", None, False)]
    tray = TrackingSpec("idealo", "1", URL, include_regex="qrevo", exclude_regex=r"\(t\)")
    assert all(is_valid(o, spec) for o in ok)
    assert not any(is_valid(o, tray) for o in bad)


def test_include_regex_can_be_order_insensitive_with_lookaheads():
    spec = TrackingSpec("idealo", "1", URL, include_regex=r"(?=.*9070(?!\s*xt))(?=.*challenger)")
    assert is_valid(IdealoOffer("ASRock Challenger AMD Radeon RX 9070 16GB", 864, "tienda.es", None, False), spec)
    assert not is_valid(IdealoOffer("ASRock Challenger RX 9070 XT", 900, "tienda.es", None, False), spec)


def test_source_uses_injected_fetcher_and_raises_on_empty_page():
    calls = []

    def fetch(url):
        calls.append(url)
        return page()

    q = IdealoPriceSource(fetch, delay_s=0).lookup(SPEC)
    assert calls == [URL] and q.price == 1221.97
    with pytest.raises(RuntimeError):
        IdealoPriceSource(lambda u: "<html></html>", delay_s=0).lookup(SPEC)


# ---------- histórico append-only ----------

def _obs(price, offer_id="m10", at=NOW):
    return PriceObservation(offer_id, at, price, "€", "carrefour.es", "idealo", URL, 7)


def test_jsonl_history_roundtrip_and_append_only(tmp_path):
    h = JsonlPriceHistory(tmp_path / "obs.jsonl")
    assert h.observations("m10") == []
    h.record(_obs(1200))
    h.record(_obs(1100, "otro"))
    h2 = JsonlPriceHistory(tmp_path / "obs.jsonl")
    assert [o.price for o in h2.observations("m10")] == [1200]
    assert h2.observations("m10")[0].at == NOW
    h2.record(_obs(1150))
    lines = (tmp_path / "obs.jsonl").read_text().splitlines()
    assert len(lines) == 3


def test_jsonl_history_ignores_corrupt_lines(tmp_path):
    p = tmp_path / "obs.jsonl"
    JsonlPriceHistory(p).record(_obs(1200))
    with p.open("a") as f:
        f.write("{roto\n")
    assert [o.price for o in JsonlPriceHistory(p).observations("m10")] == [1200]


# ---------- trabajo de refresco ----------

class MemHistory:
    def __init__(self):
        self.rows = []

    def record(self, obs):
        self.rows.append(obs)

    def observations(self, offer_id):
        return [o for o in self.rows if o.offer_id == offer_id]


class FakeSource:
    def __init__(self, results):
        self.results = results

    def lookup(self, spec):
        r = self.results[spec.product_id]
        if isinstance(r, Exception):
            raise r
        return r


class FixedNow:
    def now(self):
        return NOW


def test_refresh_records_successes_skips_failures_and_untracked():
    tracked = make_offer(id="a", tracking=TrackingSpec("idealo", "1", "https://i/1"))
    broken = make_offer(id="b", tracking=TrackingSpec("idealo", "2", "https://i/2"))
    empty = make_offer(id="c", tracking=TrackingSpec("idealo", "3", "https://i/3"))
    untracked = make_offer(id="d")
    src = FakeSource({"1": SourceQuote(99.0, "tienda", "t", "https://i/1", 5, 2),
                      "2": RuntimeError("HTTP 403"), "3": None})
    hist = MemHistory()
    report = RefreshJob(FakeRepo([tracked, broken, empty, untracked]), src, hist, FixedNow()).run()
    assert [(o.offer_id, o.price, o.at) for o in hist.rows] == [("a", 99.0, NOW)]
    assert report.ok == ["a"] and report.no_valid == ["c"] and list(report.failed) == ["b"]
    assert "403" in report.failed["b"]
    assert report.tracked == 3
    assert not report.all_failed


def test_refresh_all_failed_flag():
    o = make_offer(id="a", tracking=TrackingSpec("idealo", "1", "https://i/1"))
    report = RefreshJob(FakeRepo([o]), FakeSource({"1": RuntimeError("x")}), MemHistory(), FixedNow()).run()
    assert report.all_failed


def test_refresh_only_selected_ids():
    a = make_offer(id="a", tracking=TrackingSpec("idealo", "1", "https://i/1"))
    b = make_offer(id="b", tracking=TrackingSpec("idealo", "2", "https://i/2"))
    q = SourceQuote(1.0, "s", "t", "u", 1, 1)
    hist = MemHistory()
    RefreshJob(FakeRepo([a, b]), FakeSource({"1": q, "2": q}), hist, FixedNow()).run(only={"b"})
    assert [o.offer_id for o in hist.rows] == ["b"]
