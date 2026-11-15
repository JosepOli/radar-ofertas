"""Capa HTTP (FastAPI). Solo traduce peticiones a casos de uso; no contiene reglas de negocio."""
from __future__ import annotations

import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from radar.adapters.clock import SystemClock
from radar.adapters.images import BingThumbnailProvider, FileImageCache
from radar.adapters.json_repository import JsonSeedRepository
from radar.adapters.jsonl_history import JsonlPriceHistory
from radar.application.services import CatalogService, OfferNotFound, PhotoService
from radar.domain.catalog import OfferQuery

STATIC = Path(__file__).parent / "static"


def _sniff(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def create_app(catalog: CatalogService, photos: PhotoService) -> FastAPI:
    app = FastAPI(title="Radar de ofertas", version="0.2.0")

    @app.get("/api/meta")
    def meta():
        return catalog.meta()

    @app.get("/api/sections")
    def sections():
        return catalog.sections()

    @app.get("/api/markets")
    def markets():
        return catalog.markets()

    @app.get("/api/offers")
    def offers(
        section: str | None = None,
        q: str = "",
        verdict: str = "all",
        max_price: float | None = Query(default=None, ge=0),
        only_below_low: bool = False,
        sort: str = "rec",
    ):
        try:
            return catalog.search(OfferQuery(section, q, verdict, max_price, only_below_low, sort))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/offers/{offer_id}")
    def offer(offer_id: str):
        try:
            return catalog.get(offer_id)
        except OfferNotFound:
            raise HTTPException(status_code=404, detail="Oferta no encontrada")

    @app.get("/data.json")
    def data():
        p = catalog.payload()
        p["meta"]["mode"] = "server"
        return p

    @app.get("/img/{offer_id}")
    def image(offer_id: str):
        try:
            data = photos.photo(offer_id)
        except OfferNotFound:
            raise HTTPException(status_code=404, detail="Oferta no encontrada")
        if data is None:
            return Response(status_code=204)
        return Response(content=data, media_type=_sniff(data), headers={"Cache-Control": "private, max-age=3600"})

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    for name in ("radar-core.js", "art.js"):
        app.add_api_route(f"/{name}", (lambda n=name: FileResponse(STATIC / n)), methods=["GET"])
    app.mount("/fonts", StaticFiles(directory=STATIC / "fonts"), name="fonts")
    return app


def build_from_env() -> FastAPI:
    """Composición raíz: aquí se eligen las implementaciones concretas."""
    seed = os.environ.get("RADAR_SEED", "data/seed.json")
    history = os.environ.get("RADAR_HISTORY", "data/observations.jsonl")
    image_dir = os.environ.get("RADAR_IMAGE_DIR", "data/images")
    fetch = os.environ.get("RADAR_FETCH_IMAGES", "1") == "1"
    repo = JsonSeedRepository(seed)
    provider = None
    if fetch:
        client = httpx.Client(
            timeout=10,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) RadarOfertas/0.2", "Accept-Language": "es-ES,es;q=0.9"},
        )
        provider = BingThumbnailProvider(client)
    catalog = CatalogService(repo, SystemClock(), JsonlPriceHistory(history))
    return create_app(catalog, PhotoService(repo, FileImageCache(image_dir), provider))
