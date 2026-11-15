from datetime import date

import pytest

from radar.domain.catalog import OfferQuery, effective_discount, run_query
from radar.domain.models import Verdict

from .conftest import TODAY, make_offer

A = make_offer(id="a", name="Dreame Matrix10", price=649, reference_price=1299, annual_low=735,
               verdict=Verdict.BUY, rank=1, ends_on=date(2026, 11, 30), tags=("30.000 Pa",))
B = make_offer(id="b", name="Roborock Q7", price=129, reference_price=299, verdict=Verdict.SKIP, rank=3)
C = make_offer(id="c", section="gpu", name="RTX 5090", price=7492, reference_price=2369, verdict=Verdict.AVOID, rank=1)
D = make_offer(id="d", section="print", name="Filamento", price=None, discount_override=47, verdict=Verdict.BUY,
               rank=1, ends_on=date(2026, 12, 1))
ALL = [A, B, C, D]


def ids(res):
    return [o.id for o in res]


def test_default_query_returns_everything_grouped_by_section_and_rank():
    assert set(ids(run_query(ALL, OfferQuery(), TODAY))) == {"a", "b", "c", "d"}


def test_filter_by_section_and_text_is_case_insensitive():
    assert ids(run_query(ALL, OfferQuery(section="robots", text="matrix"), TODAY)) == ["a"]
    assert ids(run_query(ALL, OfferQuery(text="30.000 PA"), TODAY)) == ["a"]


@pytest.mark.parametrize("group,expected", [("buy", {"a", "d"}), ("top", {"a", "d"}), ("skip", {"b", "c"})])
def test_verdict_groups(group, expected):
    assert set(ids(run_query(ALL, OfferQuery(verdict_group=group), TODAY))) == expected


def test_max_price_keeps_items_without_price():
    assert set(ids(run_query(ALL, OfferQuery(max_price=500), TODAY))) == {"b", "d"}


def test_only_below_annual_low():
    assert ids(run_query(ALL, OfferQuery(only_below_annual_low=True), TODAY)) == ["a"]


def test_sort_by_discount_orders_biggest_first_and_price_rises_last():
    assert effective_discount(B) == 57 and effective_discount(A) == 50
    assert ids(run_query([A, B], OfferQuery(sort="disc"), TODAY)) == ["b", "a"]
    rise = make_offer(id="r", price=200, reference_price=100, rank=0)
    assert ids(run_query([rise, A], OfferQuery(sort="disc"), TODAY)) == ["a", "r"]


def test_effective_discount_prefers_override():
    assert effective_discount(D) == 47


def test_unknown_sort_or_group_is_rejected():
    with pytest.raises(ValueError):
        run_query(ALL, OfferQuery(sort="nope"), TODAY)
    with pytest.raises(ValueError):
        run_query(ALL, OfferQuery(verdict_group="nope"), TODAY)


def test_sort_by_end_date_puts_open_ended_last():
    res = run_query([B, A], OfferQuery(section="robots", sort="end"), TODAY)
    assert ids(res) == ["a", "b"]
