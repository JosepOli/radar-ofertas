"""Categorías madre: el seed declara `groups` y cada sección dice a cuál pertenece."""
import json

import pytest

from radar.adapters.json_repository import JsonSeedRepository, SeedError
from radar.application.services import CatalogService
from radar.domain.models import Group, Section

from .conftest import SEED, FakeRepo, make_offer


def _seed(tmp_path, mutate):
    raw = json.loads(SEED.read_text(encoding="utf-8"))
    raw.pop("groups", None)
    for s in raw["sections"]:
        s.pop("group", None)
    mutate(raw)
    p = tmp_path / "seed.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    return p


def _grouped(raw):
    raw["groups"] = [{"id": "a", "title": "Grupo A"}, {"id": "b", "title": "Grupo B"}]
    for i, s in enumerate(raw["sections"]):
        s["group"] = "a" if i % 2 == 0 else "b"


def test_domain_defaults():
    assert Section("x", "X", "i").group is None
    assert Group("a", "A") == Group(id="a", title="A")


def test_seed_without_groups_still_loads(tmp_path):
    repo = JsonSeedRepository(_seed(tmp_path, lambda r: None))
    assert repo.groups() == ()
    assert all(s.group is None for s in repo.sections())


def test_parses_groups_in_order(tmp_path):
    repo = JsonSeedRepository(_seed(tmp_path, _grouped))
    assert [g.id for g in repo.groups()] == ["a", "b"]
    assert repo.sections()[0].group == "a" and repo.sections()[1].group == "b"


@pytest.mark.parametrize("mutate,msg", [
    (lambda r: (_grouped(r), r["sections"][0].__setitem__("group", "zz")), "grupo desconocido"),
    (lambda r: (_grouped(r), r["sections"][0].pop("group")), "sin grupo"),
    (lambda r: (_grouped(r), r["groups"].append({"id": "a", "title": "Otra"})), "duplicado"),
    (lambda r: (_grouped(r), r["groups"].append({"id": "Mal id", "title": "X"})), "id de grupo"),
    (lambda r: (_grouped(r), r["groups"].append({"id": "c", "title": ""})), "título"),
    (lambda r: (_grouped(r), r["groups"].append({"id": "vacio", "title": "Vacío"})), "sin secciones"),
    (lambda r: r["sections"][0].__setitem__("group", "a"), "grupo desconocido"),
])
def test_rejects_bad_groups(tmp_path, mutate, msg):
    with pytest.raises(SeedError, match=msg):
        JsonSeedRepository(_seed(tmp_path, mutate))


def test_payload_exposes_groups_with_sections_and_counts(clock):
    secs = (Section("s1", "S1", "i", group="g1"), Section("s2", "S2", "i", group="g1"),
            Section("s3", "S3", "i", group="g2"))
    offers = [make_offer(id="o1", section="s1"), make_offer(id="o2", section="s2"),
              make_offer(id="o3", section="s3"), make_offer(id="o4", section="s3")]
    repo = FakeRepo(offers, sections=secs, groups=(Group("g1", "Uno"), Group("g2", "Dos")))
    p = CatalogService(repo, clock).payload()
    assert p["groups"] == [
        {"id": "g1", "title": "Uno", "sections": ["s1", "s2"], "count": 2},
        {"id": "g2", "title": "Dos", "sections": ["s3"], "count": 2},
    ]
    assert [s["group"] for s in p["sections"]] == ["g1", "g1", "g2"]


def test_payload_groups_empty_when_seed_has_none(clock):
    repo = FakeRepo([make_offer(section="s1")], sections=(Section("s1", "S1", "i"),))
    assert CatalogService(repo, clock).payload()["groups"] == []
