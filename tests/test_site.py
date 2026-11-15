import json
import re
from datetime import datetime, timezone

from radar.adapters.static_site import write_site
from radar.application.services import CatalogService
from radar.domain.models import PriceObservation, Section, TrackingSpec, Verdict

from .conftest import TODAY, FakeRepo, make_offer
from .test_live_prices import MemHistory

NOW = datetime(2026, 11, 15, 17, tzinfo=timezone.utc)


class Clock:
    def today(self):
        return TODAY

    def now(self):
        return NOW


def _catalog(history=None):
    o = make_offer(id="m10", name="Matrix10", price=649, reference_price=1299, annual_low=735, verdict=Verdict.BUY,
                   tracking=TrackingSpec("idealo", "1", "https://www.idealo.es/precios/1/x.html"),
                   image_url="https://cdn.idealo.com/x.jpg")
    plain = make_offer(id="p", name="Sin seguimiento", price=10)
    repo = FakeRepo([o, plain], sections=[Section("robots", "Robots", "intro")])
    return CatalogService(repo, Clock(), history)


def test_view_includes_live_market_price_from_history():
    h = MemHistory()
    h.record(PriceObservation("m10", NOW.replace(hour=9), 1250, "€", "worten.es", "idealo", "https://i", 7))
    h.record(PriceObservation("m10", NOW.replace(hour=15), 1221.97, "€", "carrefour.es", "idealo", "https://i", 7))
    v = _catalog(h).get("m10")
    live = v["live"]
    assert live["price"] == 1221.97 and live["shop"] == "carrefour.es"
    assert live["lowest"] == 1221.97 and live["count"] == 2
    assert live["offer_vs_market_pct"] == -47      # la oferta es un 47 % más barata que el resto del mercado
    assert live["source"] == "idealo" and live["url"].startswith("https://")
    assert v["tracking"]["url"].startswith("https://www.idealo.es/")
    assert v["image_url"] == "https://cdn.idealo.com/x.jpg"


def test_view_without_history_has_no_live_block():
    assert _catalog().get("m10")["live"] is None
    assert _catalog(MemHistory()).get("p")["live"] is None


def test_payload_contains_everything_the_static_site_needs():
    p = _catalog(MemHistory()).payload()
    assert set(p) >= {"meta", "sections", "markets", "offers"}
    assert p["meta"]["generated_at"].startswith("2026-11-15T17:00")
    assert [o["id"] for o in p["offers"]] == ["m10", "p"]
    assert p["sections"][0]["count"] == 2


def test_write_site_creates_noindex_static_bundle(tmp_path):
    out = tmp_path / "dist"
    write_site(_catalog(MemHistory()).payload(), out)
    html = (out / "index.html").read_text()
    assert '<meta name="robots" content="noindex, nofollow">' in html
    assert "fonts.googleapis.com" not in html and "fonts.gstatic.com" not in html
    assert (out / "robots.txt").read_text().strip().endswith("Disallow: /")
    assert (out / ".nojekyll").exists()
    data = json.loads((out / "data.json").read_text())
    assert data["offers"][0]["id"] == "m10"
    assert (out / "radar-core.js").exists()
    fonts = list((out / "fonts").glob("*.woff2"))
    assert fonts, "las fuentes deben servirse desde el propio sitio"
    css_refs = set(re.findall(r"fonts/([\w.-]+\.woff2)", html))
    assert css_refs and css_refs <= {f.name for f in fonts}
