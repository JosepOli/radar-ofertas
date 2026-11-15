import html
import json

import httpx
import pytest

from radar.adapters.images import BingThumbnailProvider, FileImageCache


def _bing_page(*turls):
    items = "".join(
        f'<a class="iusc" m="{html.escape(json.dumps({"turl": t, "murl": "https://x/y.jpg"}))}" href="#">x</a>'
        for t in turls
    )
    return f"<html><body>{items}</body></html>"


def test_cache_roundtrip_and_key_sanitising(tmp_path):
    c = FileImageCache(tmp_path)
    assert c.get("dreame-matrix10") is None
    c.put("dreame-matrix10", b"abc")
    assert c.get("dreame-matrix10") == b"abc"
    c.put("../../etc/passwd", b"z")  # se sanea, nunca sale del directorio
    assert all(p.parent == tmp_path for p in tmp_path.iterdir())
    with pytest.raises(ValueError):
        c.get("///")


def test_thumbnail_urls_parse_escaped_metadata():
    page = _bing_page("https://tse1.mm.bing.net/th?id=A", "https://tse2.mm.bing.net/th?id=B")
    assert BingThumbnailProvider.thumbnail_urls(page) == [
        "https://tse1.mm.bing.net/th?id=A", "https://tse2.mm.bing.net/th?id=B"]


def test_find_skips_broken_candidates_and_returns_first_image():
    page = _bing_page("https://tse1.mm.bing.net/th?id=BAD", "https://tse2.mm.bing.net/th?id=OK")

    def handler(req: httpx.Request):
        if req.url.host == "www.bing.com":
            return httpx.Response(200, text=page)
        if "BAD" in str(req.url):
            return httpx.Response(404)
        return httpx.Response(200, content=b"\xff\xd8\xffimg", headers={"content-type": "image/jpeg"})

    prov = BingThumbnailProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    assert prov.find("Dreame Matrix10") == b"\xff\xd8\xffimg"


def test_find_returns_none_without_results():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html></html>")))
    assert BingThumbnailProvider(client).find("nada") is None
