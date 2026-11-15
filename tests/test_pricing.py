from datetime import date

import pytest

from radar.domain.pricing import days_left, discount_pct, is_below_annual_low, to_eur, vs_annual_low_pct


@pytest.mark.parametrize("price,ref,expected", [
    (649, 1299, 50), (599, 999, 40), (7492, 2369, -216), (None, 100, None), (100, None, None), (100, 0, None),
])
def test_discount_pct(price, ref, expected):
    assert discount_pct(price, ref) == expected


def test_vs_annual_low_negative_means_cheaper_than_ever():
    assert vs_annual_low_pct(649, 735) == -12
    assert vs_annual_low_pct(409.9, 329.66) == 24
    assert vs_annual_low_pct(368, 368) == 0
    assert vs_annual_low_pct(None, 368) is None


def test_below_annual_low_is_strict():
    assert is_below_annual_low(599, 629)
    assert not is_below_annual_low(368, 368)
    assert not is_below_annual_low(None, 368)
    assert not is_below_annual_low(100, None)


def test_days_left_counts_calendar_days():
    assert days_left(date(2026, 11, 30), date(2026, 11, 15)) == 15
    assert days_left(date(2026, 11, 14), date(2026, 11, 15)) == -1
    assert days_left(None, date(2026, 11, 15)) is None


def test_to_eur_uses_rate_and_rejects_unknown_currency():
    assert to_eur(100, "$", {"$": 0.86}) == pytest.approx(86)
    assert to_eur(None, "$", {"$": 0.86}) is None
    with pytest.raises(ValueError):
        to_eur(1, "¥", {"$": 0.86})
