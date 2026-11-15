import pytest
from fastapi.testclient import TestClient

from radar.application.services import CatalogService, PhotoService
from radar.web.app import create_app


class MemCache:
    def __init__(self): self.s = {}
    def get(self, k): return self.s.get(k)
    def put(self, k, v): self.s[k] = v


class Prov:
    def find(self, q): return b"\x89PNG\r\n\x1a\nfake"


@pytest.fixture
def client(seed_repo, clock):
    return TestClient(create_app(CatalogService(seed_repo, clock), PhotoService(seed_repo, MemCache(), Prov())))


def test_index_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Radar" in r.text


def test_sections_and_markets(client):
    assert len(client.get("/api/sections").json()) >= 9
    assert len(client.get("/api/markets").json()) == 11


def test_offers_filters(client):
    robots = client.get("/api/offers", params={"section": "robots"}).json()
    assert robots and all(o["section"] == "robots" for o in robots)
    top = client.get("/api/offers", params={"verdict": "top"}).json()
    assert top and all(o["verdict"] == "top" for o in top)


def test_bad_sort_is_422(client):
    assert client.get("/api/offers", params={"sort": "nope"}).status_code == 422


def test_offer_detail_and_404(client):
    oid = client.get("/api/offers").json()[0]["id"]
    assert client.get(f"/api/offers/{oid}").json()["id"] == oid
    assert client.get("/api/offers/nope").status_code == 404


def test_image_endpoint_sniffs_type(client):
    oid = client.get("/api/offers").json()[0]["id"]
    r = client.get(f"/img/{oid}")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert client.get("/img/nope").status_code == 404
