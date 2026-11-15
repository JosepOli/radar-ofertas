"""Genera el sitio estático (GitHub Pages u otro hosting de ficheros): HTML + JS + fuentes + data.json."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

STATIC = Path(__file__).resolve().parents[1] / "web" / "static"
ASSETS = ("index.html", "radar-core.js", "art.js")

ROBOTS = "User-agent: *\nDisallow: /\n"


def write_site(payload: dict[str, Any], out: str | Path) -> Path:
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name in ASSETS:
        shutil.copy2(STATIC / name, out / name)
    shutil.copytree(STATIC / "fonts", out / "fonts")
    data = {**payload, "meta": {**payload["meta"], "mode": "static"}}
    (out / "data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out / "robots.txt").write_text(ROBOTS, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return out
