# Radar Black Friday 2026

Ofertas de tecnología comparadas con **lo que han costado durante el año** y con **lo que piden ahora otras tiendas**, no con el PVP inflado. Cada producto tiene un veredicto (Comprar, Buena opción, Pasa, No comprar), sus fuentes y su plazo.

Proyecto personal, sin afiliados ni publicidad. Los veredictos son editoriales; los precios cambian rápido: confirma siempre el precio final en la tienda.

## Cómo funciona

| Dato | De dónde sale | Cada cuánto |
|---|---|---|
| Precio de la oferta, referencia, mínimo anual, veredicto y notas | `data/seed.json`, revisado a mano con fuentes enlazadas | Cuando cambia una campaña |
| Precio actual en otras tiendas | Ficha exacta del producto en idealo.es: mejor oferta de tienda fiable, envío incluido, sin vendedores externos de marketplaces ni usados | Varias veces al día |
| Histórico propio | `data/observations.jsonl`, append-only | Cada lectura |

El refresco **solo añade observaciones**; nunca toca veredictos ni textos. Una lectura fallida no se registra: la página muestra la última buena y su antigüedad.

## Uso

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev,refresh]'
pytest && node --test tests/js/*.test.js
python -m radar.cli refresh            # lee precios (necesita curl_cffi)
python -m radar.cli build --out dist   # genera el sitio estático
python -m http.server -d dist 8000     # verlo en local
```

Modo servidor en una LAN (opcional): `uvicorn --factory radar.web.app:build_from_env --port 8080`, `docker compose up -d` o la unidad de `deploy/`.

## Estructura

```
src/radar/
  domain/        modelos, precios, búsqueda (sin tildes, multi-término), filtros, histórico (sin E/S)
  application/   puertos, catálogo, refresco de precios
  adapters/      seed JSON, histórico JSONL, idealo, sitio estático, fotos, relojes
  web/           FastAPI y frontend (static/: index.html, radar-core.js, art.js, fuentes)
tests/           pytest + node --test (tests/js); fixtures con HTML real de idealo
```

Publicación: cada push a `main` pasa las pruebas, genera `dist/` y lo despliega en GitHub Pages (`.github/workflows/pages.yml`). La página no se indexa en buscadores (`noindex` y `robots.txt`).

## Licencias

Código: MIT. Fuentes tipográficas (Chakra Petch, IBM Plex): SIL OFL 1.1, ver `src/radar/web/static/fonts/OFL.txt`. Las fotos de producto se enlazan desde idealo y son de sus titulares.
