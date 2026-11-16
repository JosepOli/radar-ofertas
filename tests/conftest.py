from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from radar.adapters.clock import FixedClock
from radar.adapters.json_repository import JsonSeedRepository
from radar.domain.models import Offer, Source, Verdict

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed.json"
TODAY = date(2026, 11, 15)


@pytest.fixture
def clock():
    return FixedClock(TODAY)


@pytest.fixture(scope="session")
def seed_repo():
    return JsonSeedRepository(SEED)


def make_offer(**kw) -> Offer:
    base = dict(
        id="x", section="robots", name="Robot X", store="Tienda", currency="€",
        verdict=Verdict.GOOD, rank=1, link="https://example.org",
        sources=(Source("Fuente", "https://example.org"),),
    )
    base.update(kw)
    return Offer(**base)


class FakeRepo:
    def __init__(self, offers, sections=(), markets=(), fx=None, groups=()):
        self._o, self._s, self._m = tuple(offers), tuple(sections), tuple(markets)
        self._g = tuple(groups)
        self._fx = fx or {"€": 1.0, "$": 0.86}

    def offers(self): return self._o
    def sections(self): return self._s
    def groups(self): return self._g
    def markets(self): return self._m
    def fx_to_eur(self): return self._fx
    def checked_on(self): return TODAY
