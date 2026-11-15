"""Adaptadores de imagen: caché en disco y búsqueda de miniaturas en Bing Imágenes."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import httpx

_SAFE = re.compile(r"[^a-z0-9-]")


class FileImageCache:
    """Guarda una imagen por oferta en un directorio. La clave se sanea para evitar rutas raras."""

    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = _SAFE.sub("", key.lower())
        if not safe:
            raise ValueError("Clave de imagen vacía")
        return self._dir / f"{safe}.img"

    def get(self, key: str) -> bytes | None:
        p = self._path(key)
        return p.read_bytes() if p.exists() else None

    def put(self, key: str, data: bytes) -> None:
        tmp = self._path(key).with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(self._path(key))


_M_ATTR = re.compile(r'class="iusc"[^>]*?\sm="([^"]+)"|\sm="([^"]+)"[^>]*?class="iusc"')


class BingThumbnailProvider:
    """Busca la consulta en Bing Imágenes y descarga la miniatura del primer resultado válido.

    Uso personal: las miniaturas de Bing (th.bing.com / *.mm.bing.net) son ligeras y estables.
    """

    SEARCH_URL = "https://www.bing.com/images/search"

    def __init__(self, client: httpx.Client, max_candidates: int = 4, size: int = 480) -> None:
        self._client = client
        self._max = max_candidates
        self._size = size

    def find(self, query: str) -> bytes | None:
        r = self._client.get(self.SEARCH_URL, params={"q": query, "qft": "+filterui:photo-photo", "first": 1})
        r.raise_for_status()
        for turl in self.thumbnail_urls(r.text)[: self._max]:
            sep = "&" if "?" in turl else "?"
            img = self._client.get(f"{turl}{sep}w={self._size}&h={self._size}&c=7&rs=1&p=0")
            if img.status_code == 200 and img.headers.get("content-type", "").startswith("image/"):
                return img.content
        return None

    @staticmethod
    def thumbnail_urls(page_html: str) -> list[str]:
        urls: list[str] = []
        for m in _M_ATTR.finditer(page_html):
            raw = m.group(1) or m.group(2)
            try:
                meta = json.loads(html.unescape(raw))
            except json.JSONDecodeError:
                continue
            if turl := meta.get("turl"):
                urls.append(turl)
        return urls
