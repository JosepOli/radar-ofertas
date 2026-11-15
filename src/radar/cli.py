"""Utilidades de línea de comandos.

    python -m radar.cli refresh [--only id1,id2]   # lee precios reales (idealo) y los añade al histórico
    python -m radar.cli build [--out dist]         # genera el sitio estático (sin red)
    python -m radar.cli warm                       # precarga fotos en la caché local (solo modo servidor LAN)

Variables: RADAR_SEED (data/seed.json), RADAR_HISTORY (data/observations.jsonl), RADAR_IMAGE_DIR (data/images).
Código de salida de refresh: 0 si al menos una lectura fue bien; 3 si todas fallaron (bloqueo o cambio de idealo).
"""
from __future__ import annotations

import argparse
import logging
import os

from radar.adapters.clock import SystemClock
from radar.adapters.json_repository import JsonSeedRepository
from radar.adapters.jsonl_history import JsonlPriceHistory


def _repo():
    return JsonSeedRepository(os.environ.get("RADAR_SEED", "data/seed.json"))


def _history():
    return JsonlPriceHistory(os.environ.get("RADAR_HISTORY", "data/observations.jsonl"))


def refresh(only: set[str] | None, delay: float) -> int:
    from radar.adapters.idealo import IdealoPriceSource, curl_cffi_fetcher
    from radar.application.refresh import RefreshJob

    report = RefreshJob(_repo(), IdealoPriceSource(curl_cffi_fetcher(), delay_s=delay), _history(), SystemClock()).run(only)
    print(report.summary())
    return 3 if report.all_failed else 0


def build(out: str) -> int:
    from radar.adapters.static_site import write_site
    from radar.application.services import CatalogService

    payload = CatalogService(_repo(), SystemClock(), _history()).payload()
    path = write_site(payload, out)
    live = sum(1 for o in payload["offers"] if o["live"])
    print(f"Sitio generado en {path}: {len(payload['offers'])} ofertas, {live} con precio vigilado.")
    return 0


def warm() -> int:
    import httpx

    from radar.adapters.images import BingThumbnailProvider, FileImageCache
    from radar.application.services import PhotoService

    client = httpx.Client(timeout=10, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) RadarOfertas/0.2"})
    svc = PhotoService(_repo(), FileImageCache(os.environ.get("RADAR_IMAGE_DIR", "data/images")),
                       BingThumbnailProvider(client))
    result = svc.warm_all()
    missing = [k for k, ok in result.items() if not ok]
    print(f"Fotos: {len(result) - len(missing)}/{len(result)}")
    for k in missing:
        print("  sin foto:", k)
    return 0 if not missing else 1


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="radar", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("refresh")
    r.add_argument("--only", default="", help="ids separados por comas")
    r.add_argument("--delay", type=float, default=3.0, help="segundos entre peticiones")
    b = sub.add_parser("build")
    b.add_argument("--out", default="dist")
    sub.add_parser("warm")
    a = ap.parse_args(argv)
    if a.cmd == "refresh":
        return refresh({x for x in a.only.split(",") if x} or None, a.delay)
    if a.cmd == "build":
        return build(a.out)
    return warm()


if __name__ == "__main__":
    raise SystemExit(main())
