"""The region's map, served from two committed files.

resources/map/region.pmtiles is an OpenStreetMap extract of the Kabul--
Parwan--Ghorband box, fetched once at a developer's desk; geometry.json is
the shape of the roads the product actually drives, asked of a routing
engine the same way, once. Production serves both as static bytes. There is
no tile provider to pay, no API key to leak, no quota to hit and nothing to
break at three in the morning: the map is data in the repository, like the
locale files.

The journey line for a trip is resolved here too. Most trips run along one
of two valley corridors, so a trip's shape is a slice of a corridor between
the points nearest its two ends -- which means a station gets a proper road
line the day it gets coordinates, with no routing call for it ever made.
"""

from __future__ import annotations

import gzip
import json
import math
import threading
from functools import lru_cache
from pathlib import Path

from pmtiles.reader import MmapSource, Reader

_MAP_DIR = Path(__file__).resolve().parent.parent.parent / "resources" / "map"

#: A slice endpoint may sit this far off the corridor before the slice is
#: judged a lie. Wide enough for a station on a bazaar street one block off
#: the highway; far too narrow to pass a journey from the wrong valley.
_MAX_SNAP_M = 5_000


class _Tiles:
    """One shared reader over the archive, guarded: mmap reads are cheap but
    the reader object itself is not documented thread-safe."""

    def __init__(self, path: Path) -> None:
        self._file = open(path, "rb")
        self._reader = Reader(MmapSource(self._file))
        self._lock = threading.Lock()

    def get(self, z: int, x: int, y: int) -> bytes | None:
        with self._lock:
            data = self._reader.get(z, x, y)
        if data is None:
            return None
        # Stored gzip-compressed; served plain so no client has to agree
        # about Content-Encoding.
        if data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)
        return data


@lru_cache(maxsize=1)
def tiles() -> _Tiles:
    return _Tiles(_MAP_DIR / "region.pmtiles")


@lru_cache(maxsize=1)
def _legs() -> dict[str, dict]:
    raw = json.loads((_MAP_DIR / "geometry.json").read_text(encoding="utf-8"))
    return raw["legs"]


def glyphs_path(fontstack: str, span: str) -> Path | None:
    """The pre-rendered label glyphs MapLibre asks for, range by range."""
    candidate = (_MAP_DIR / "glyphs" / fontstack / f"{span}.pbf").resolve()
    # A fontstack is client-supplied text; it must not walk the filesystem.
    if not str(candidate).startswith(str((_MAP_DIR / "glyphs").resolve())):
        return None
    return candidate if candidate.is_file() else None


def _metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Equirectangular; exact enough for snapping at valley scale."""
    dx = (a[0] - b[0]) * 111_320 * math.cos(math.radians((a[1] + b[1]) / 2))
    dy = (a[1] - b[1]) * 110_574
    return math.hypot(dx, dy)


def _nearest(points: list[list[float]], target: tuple[float, float]) -> tuple[int, float]:
    best_i, best_d = 0, float("inf")
    for i, point in enumerate(points):
        d = _metres((point[0], point[1]), target)
        if d < best_d:
            best_i, best_d = i, d
    return best_i, best_d


def journey_line(
    origin_code: str | None,
    dest_code: str | None,
    origin: tuple[float, float] | None,
    dest: tuple[float, float] | None,
) -> list[list[float]] | None:
    """The road between a trip's two ends, as (lon, lat) points.

    An exact precomputed pair wins; otherwise the best corridor slice. None
    means the honest answer is "no line" -- an endpoint with no coordinates,
    or ends that do not sit on any road this file knows.
    """
    if origin is None or dest is None:
        return None

    exact = _legs().get(f"pair:{origin_code}:{dest_code}")
    if exact:
        return exact["points"]
    reverse = _legs().get(f"pair:{dest_code}:{origin_code}")
    if reverse:
        return list(reversed(reverse["points"]))

    best: list[list[float]] | None = None
    best_score = float("inf")
    for leg in _legs().values():
        points = leg["points"]
        i, d_from = _nearest(points, origin)
        j, d_to = _nearest(points, dest)
        if d_from > _MAX_SNAP_M or d_to > _MAX_SNAP_M or i == j:
            continue
        score = d_from + d_to
        if score < best_score:
            lo, hi = min(i, j), max(i, j)
            cut = points[lo : hi + 1]
            best = cut if i <= j else list(reversed(cut))
            best_score = score
    return best
