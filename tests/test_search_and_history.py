from datetime import date, datetime, timezone

import pytest

from radar.domain.catalog import OfferQuery, run_query
from radar.domain.history import summarize
from radar.domain.models import PriceObservation, Verdict
from radar.domain.text import matches_all_terms, normalize

from .conftest import TODAY, make_offer

FX = {"€": 1.0, "$": 0.86}


def ids(res):
    return [o.id for o in res]


def test_normalize_strips_accents_case_and_punctuation_spacing():
    assert normalize("Impresión  3D · ÚLTIMA") == "impresion 3d · ultima"
    assert normalize("") == ""


def test_matches_all_terms_is_accent_insensitive_and_requires_every_term():
    text = "Robot aspirador · fregado con rodillo · agua a 80 °C"
    assert matches_all_terms(text, "fregado rodillo")
    assert matches_all_terms(text, "FREGADO   Rodillo")
    assert matches_all_terms("Impresión 3D", "impresion")
    assert not matches_all_terms(text, "fregado mopas")
    assert matches_all_terms(text, "   ")


def test_text_query_matches_across_fields_with_accents_and_multiple_terms():
    a = make_offer(id="a", name="Dreame Aqua10 Ultra Roller", note="Fregado con rodillo", tags=("30.000 Pa",))
    b = make_offer(id="b", name="Roborock Qrevo", note="Mopas giratorias")
    assert ids(run_query([a, b], OfferQuery(text="dreame RODILLO"), TODAY)) == ["a"]
    assert ids(run_query([a, b], OfferQuery(text="giratórias"), TODAY)) == ["b"]
    assert ids(run_query([a, b], OfferQuery(text="dreame mopas"), TODAY)) == []


def test_text_query_matches_highlights():
    a = make_offer(id="a", highlights=("mín. histórico",))
    assert ids(run_query([a], OfferQuery(text="historico"), TODAY)) == ["a"]


def test_max_price_compares_in_euros():
    usd = make_offer(id="usd", currency="$", price=560)   # 481,60 €
    eur = make_offer(id="eur", price=500)
    assert set(ids(run_query([usd, eur], OfferQuery(max_price=490), TODAY, FX))) == {"usd"}


def _obs(day, price, shop="Tienda", hour=9):
    return PriceObservation("x", datetime(2026, 11, day, hour, tzinfo=timezone.utc), price, "€", shop, "idealo", "https://x")


def test_summarize_history_reports_latest_lowest_and_since():
    now = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
    s = summarize([_obs(16, 700), _obs(17, 650, "B"), _obs(19, 680, "C")], now)
    assert s.latest.price == 680 and s.latest.shop == "C"
    assert s.lowest.price == 650 and s.lowest.shop == "B"
    assert s.since == date(2026, 11, 16)
    assert s.count == 3
    assert s.age_hours == pytest.approx(27)
    assert not s.is_stale


def test_summarize_marks_old_data_as_stale_and_handles_empty():
    now = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
    assert summarize([_obs(18, 700, hour=0)], now).is_stale
    assert summarize([], now) is None


def test_summarize_tie_on_lowest_keeps_earliest():
    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    s = summarize([_obs(16, 650, "A"), _obs(17, 650, "B")], now)
    assert s.lowest.shop == "A"


def test_verdict_untouched_by_queries():
    a = make_offer(id="a", verdict=Verdict.BUY)
    assert run_query([a], OfferQuery(), TODAY)[0].verdict is Verdict.BUY
