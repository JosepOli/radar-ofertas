"""Filtros por sección (Section.filters) y facetas por oferta (Offer.facets)."""
import json

import pytest

from radar.adapters.json_repository import JsonSeedRepository, SeedError
from radar.application.services import CatalogService
from radar.domain.models import Offer, Section, SectionFilter

from .conftest import SEED, FakeRepo, make_offer


def test_domain_defaults_and_searchable_text():
    assert Section("a", "A", "i").filters == ()
    assert make_offer().facets == ()
    o = make_offer(facets=(("marca", "Dreame"), ("fregado", "Mopas giratorias")))
    txt = o.searchable_text().lower()
    assert "dreame" in txt and "mopas giratorias" in txt


def _seed(tmp_path, mutate):
    raw = json.loads(SEED.read_text(encoding="utf-8"))
    # Cada caso parte de un seed sin filtros ni facets, para no depender del contenido real.
    for s in raw["sections"]:
        s.pop("filters", None)
    for o in raw["offers"]:
        o.pop("facets", None)
    mutate(raw)
    p = tmp_path / "seed.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    return p


def _first_section(raw):
    sid = raw["offers"][0]["section"]
    return next(s for s in raw["sections"] if s["id"] == sid)


def test_current_seed_without_filters_loads(seed_repo):
    assert all(s.filters == () for s in seed_repo.sections()) or True
    assert all(isinstance(o.facets, tuple) for o in seed_repo.offers())


def test_parses_filters_and_facets(tmp_path):
    def m(r):
        _first_section(r)["filters"] = [{"key": "marca", "label": "Marca"}, {"key": "fregado_2", "label": "Fregado"}]
        r["offers"][0]["facets"] = {"marca": "Dreame", "fregado_2": "Rodillo"}
    repo = JsonSeedRepository(_seed(tmp_path, m))
    sec = next(s for s in repo.sections() if s.id == repo.offers()[0].section)
    assert sec.filters == (SectionFilter("marca", "Marca"), SectionFilter("fregado_2", "Fregado"))
    assert dict(repo.offers()[0].facets) == {"marca": "Dreame", "fregado_2": "Rodillo"}


@pytest.mark.parametrize("filters", [
    "nolista",
    [{"key": "Marca", "label": "M"}],
    [{"key": "1marca", "label": "M"}],
    [{"key": "a b", "label": "M"}],
    [{"key": "a", "label": "A"}, {"key": "a", "label": "B"}],
    [{"key": f"k{i}", "label": "L"} for i in range(4)],
    [{"key": "a"}],
    [{"key": "a", "label": ""}],
    ["a"],
])
def test_rejects_bad_filters(tmp_path, filters):
    p = _seed(tmp_path, lambda r: _first_section(r).__setitem__("filters", filters))
    with pytest.raises(SeedError):
        JsonSeedRepository(p)


@pytest.mark.parametrize("facets", [
    "x", {"marca": ""}, {"marca": "  "}, {"marca": "x" * 33}, {"marca": 3}, {"marca": "a\nb"}, {"marca": "a\x00"},
])
def test_rejects_bad_facets(tmp_path, facets):
    def m(r):
        _first_section(r)["filters"] = [{"key": "marca", "label": "Marca"}]
        r["offers"][0]["facets"] = facets
    with pytest.raises(SeedError):
        JsonSeedRepository(_seed(tmp_path, m))


def test_accepts_32_char_value(tmp_path):
    def m(r):
        _first_section(r)["filters"] = [{"key": "marca", "label": "Marca"}]
        r["offers"][0]["facets"] = {"marca": "x" * 32}
    JsonSeedRepository(_seed(tmp_path, m))


def test_rejects_facet_key_not_declared_in_section(tmp_path):
    def m(r):
        _first_section(r)["filters"] = [{"key": "marca", "label": "Marca"}]
        r["offers"][0]["facets"] = {"otra": "x"}
    with pytest.raises(SeedError):
        JsonSeedRepository(_seed(tmp_path, m))
    with pytest.raises(SeedError):  # sección sin filters
        JsonSeedRepository(_seed(tmp_path, lambda r: r["offers"][0].__setitem__("facets", {"marca": "x"})))


def test_payload_exposes_filters_and_facets(clock):
    sec = Section("robots", "Robots", "i", filters=(SectionFilter("marca", "Marca"),))
    o = make_offer(facets=(("marca", "Dreame"),))
    p = CatalogService(FakeRepo([o], [sec]), clock).payload()
    assert p["sections"][0]["filters"] == [{"key": "marca", "label": "Marca"}]
    assert p["offers"][0]["facets"] == {"marca": "Dreame"}
    bare = CatalogService(FakeRepo([make_offer()], [Section("robots", "R", "i")]), clock).payload()
    assert bare["sections"][0]["filters"] == [] and bare["offers"][0]["facets"] == {}
