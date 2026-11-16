"""El seed es el contrato de datos: estas pruebas impiden publicar datos incoherentes."""
import json
import os

import pytest

from radar.adapters.json_repository import JsonSeedRepository, SeedError

from .conftest import SEED


def test_seed_loads(seed_repo):
    assert len(seed_repo.offers()) >= 60
    assert len(seed_repo.markets()) == 11


def test_every_offer_has_sources_link_and_image_query(seed_repo):
    for o in seed_repo.offers():
        assert o.sources, o.id
        assert o.link.startswith("https://"), o.id
        assert o.image_query, o.id
        assert all(s.url.startswith("https://") for s in o.sources), o.id


def test_every_section_has_offers(seed_repo):
    used = {o.section for o in seed_repo.offers()}
    assert {s.id for s in seed_repo.sections()} <= used


def test_annual_low_note_present_when_low_given(seed_repo):
    for o in seed_repo.offers():
        if o.annual_low is not None:
            assert o.annual_low_note, o.id


def _write(tmp_path, mutate):
    raw = json.loads(SEED.read_text(encoding="utf-8"))
    mutate(raw)
    p = tmp_path / "seed.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    return p


def test_rejects_unknown_section(tmp_path):
    p = _write(tmp_path, lambda r: r["offers"][0].__setitem__("section", "nope"))
    with pytest.raises(SeedError):
        JsonSeedRepository(p)


def test_rejects_duplicate_ids(tmp_path):
    p = _write(tmp_path, lambda r: r["offers"].append(dict(r["offers"][0])))
    with pytest.raises(SeedError):
        JsonSeedRepository(p)


def test_rejects_unknown_currency(tmp_path):
    p = _write(tmp_path, lambda r: r["offers"][0].__setitem__("currency", "¥"))
    with pytest.raises(SeedError):
        JsonSeedRepository(p)


# Textos de entorno personal que no deben llegar al sitio público. Los nombres propios sensibles se leen de un
# fichero local fuera del repositorio (RADAR_PRIVATE_WORDS); en CI solo se comprueba la lista genérica.
GENERIC_PRIVATE = ("homelab", "garaje")


def _private_words() -> tuple[str, ...]:
    extra = os.environ.get("RADAR_PRIVATE_WORDS", os.path.expanduser("~/.hermes/private/radar-private-words.txt"))
    try:
        with open(extra, encoding="utf-8") as fh:
            return GENERIC_PRIVATE + tuple(w.strip().lower() for w in fh if w.strip())
    except FileNotFoundError:
        return GENERIC_PRIVATE


def test_public_texts_have_no_personal_references():
    blob = SEED.read_text(encoding="utf-8").lower()
    found = [w for w in _private_words() if w in blob]
    assert not found, f"Referencias personales en seed.json: {found}"


def test_tracked_offers_point_to_exact_idealo_product_pages(seed_repo):
    tracked = [o for o in seed_repo.offers() if o.tracking]
    assert len(tracked) >= 30
    for o in tracked:
        assert o.tracking.source == "idealo", o.id
        assert o.tracking.url.startswith(f"https://www.idealo.es/precios/{o.tracking.product_id}/"), o.id
        assert o.tracking.include_regex, o.id
    for o in seed_repo.offers():
        assert not o.image_url or o.image_url.startswith("https://cdn.idealo.com/"), o.id


def test_rejects_non_https_tracking(tmp_path):
    p = _write(tmp_path, lambda r: r["offers"][0].__setitem__(
        "tracking", {"source": "idealo", "product_id": "1", "url": "http://x"}))
    with pytest.raises(SeedError):
        JsonSeedRepository(p)


def test_rejects_invalid_tracking_regex(tmp_path):
    p = _write(tmp_path, lambda r: r["offers"][0].__setitem__(
        "tracking", {"source": "idealo", "product_id": "1", "url": "https://x", "include_regex": "(("}))
    with pytest.raises(SeedError):
        JsonSeedRepository(p)


def test_rejects_control_characters_in_tracking_regex(tmp_path):
    # "\b" mal escapado en JSON se convierte en un retroceso (\x08) y la regex deja de excluir nada.
    p = _write(tmp_path, lambda r: r["offers"][0].__setitem__(
        "tracking", {"source": "idealo", "product_id": "1", "url": "https://x", "exclude_regex": "pc\b"}))
    with pytest.raises(SeedError):
        JsonSeedRepository(p)
