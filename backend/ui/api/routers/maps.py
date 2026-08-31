"""The base map, served by the product's own API.

Public and unauthenticated on purpose: these bytes are OpenStreetMap's
public data, they carry nothing about any user, and the map renderer is a
poor place to teach about bearer tokens. Long cache lifetimes because the
region archive changes when somebody re-extracts it at a desk, which is
months apart.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from ui.api import mapdata

router = APIRouter(prefix="/geo/map", tags=["map"])

_TILE_HEADERS = {"Cache-Control": "public, max-age=86400"}
_STYLE_HEADERS = {"Cache-Control": "public, max-age=3600"}

#: What the drivers' handsets actually show. Hand-written against the layer
#: schema of the committed archive (pmtiles show --metadata), and deliberately
#: small: roads, water, terrain tone, boundaries and place names. `name` holds
#: the local name -- which in this region is the Persian or Pashto the product
#: already speaks.
_ROAD_KINDS = {
    "highway": ("#e8930c", 1.2, 7.0),
    "major_road": ("#f0b95a", 0.8, 5.0),
    "medium_road": ("#cfc7b8", 0.6, 4.0),
    "minor_road": ("#d9d2c5", 0.4, 3.0),
}


def _layers() -> list[dict]:
    layers: list[dict] = [
        {"id": "background", "type": "background",
         "paint": {"background-color": "#f4efe6"}},
        {"id": "earth", "type": "fill", "source": "region", "source-layer": "earth",
         "paint": {"fill-color": "#f1ebdd"}},
        {"id": "landcover", "type": "fill", "source": "region", "source-layer": "landcover",
         "paint": {"fill-color": "#e9e5d4", "fill-opacity": 0.6}},
        {"id": "water", "type": "fill", "source": "region", "source-layer": "water",
         "paint": {"fill-color": "#a9c8e4"}},
        {"id": "water-line", "type": "line", "source": "region", "source-layer": "water",
         "filter": ["==", ["geometry-type"], "LineString"],
         "paint": {"line-color": "#a9c8e4", "line-width": 1.0}},
    ]
    for kind, (colour, thin, thick) in _ROAD_KINDS.items():
        layers.append({
            "id": f"road-{kind}", "type": "line", "source": "region",
            "source-layer": "roads", "filter": ["==", ["get", "kind"], kind],
            "layout": {"line-cap": "round", "line-join": "round"},
            "paint": {
                "line-color": colour,
                "line-width": ["interpolate", ["exponential", 1.5], ["zoom"],
                               6, thin, 15, thick],
            },
        })
    layers += [
        {"id": "boundaries", "type": "line", "source": "region",
         "source-layer": "boundaries",
         "paint": {"line-color": "#b9a8c0", "line-width": 0.8,
                   "line-dasharray": [3, 2]}},
        {"id": "place-names", "type": "symbol", "source": "region",
         "source-layer": "places",
         "filter": ["in", ["get", "kind"], ["literal", ["country", "region", "locality"]]],
         "layout": {
             "text-field": ["get", "name"],
             "text-font": ["Noto Sans Regular"],
             "text-size": ["match", ["get", "kind"],
                           "region", 13, "locality", 12, 11],
         },
         "paint": {"text-color": "#4a4238", "text-halo-color": "#f8f4ec",
                   "text-halo-width": 1.2}},
    ]
    return layers


@router.get("/style.json")
def style(request: Request) -> dict:
    # Absolute URLs built from the request, so the emulator's 10.0.2.2, a
    # LAN address and a deployment all get a style that points back at the
    # host that served it.
    base = str(request.base_url).rstrip("/") + "/api/v1/geo/map"
    return {
        "version": 8,
        "name": "velro-region",
        "glyphs": base + "/glyphs/{fontstack}/{range}.pbf",
        "sources": {
            "region": {
                "type": "vector",
                "tiles": [base + "/tiles/{z}/{x}/{y}.mvt"],
                "minzoom": 0,
                "maxzoom": 15,
                "bounds": [67.9, 34.3, 69.7, 35.6],
                "attribution": "© OpenStreetMap",
            }
        },
        "layers": _layers(),
    }


@router.get("/tiles/{z}/{x}/{y}.mvt")
def tile(z: int, x: int, y: int) -> Response:
    data = mapdata.tiles().get(z, x, y)
    if data is None:
        # An empty tile, not an error: oceans of the z-pyramid are simply
        # absent from the archive, and the renderer treats 204 as "nothing
        # here", which is the truth.
        return Response(status_code=204, headers=_TILE_HEADERS)
    return Response(
        content=data, media_type="application/x-protobuf", headers=_TILE_HEADERS
    )


@router.get("/glyphs/{fontstack}/{span}.pbf")
def glyphs(fontstack: str, span: str) -> Response:
    path = mapdata.glyphs_path(fontstack, span)
    if path is None:
        return Response(status_code=404)
    return Response(
        content=path.read_bytes(),
        media_type="application/x-protobuf",
        headers=_TILE_HEADERS,
    )
