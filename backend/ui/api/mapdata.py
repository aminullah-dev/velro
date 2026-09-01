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


#: Hand-placed caution stretches, over and above what the curvature scan
#: finds. The first entry is the سیاه‌گرد bazaar-and-school stretch the
#: operator pointed at on a map: river on one side, the institute and the
#: teacher-training school on the other, children crossing. Grows by editing
#: this list; each entry is announced by the driver app when he enters it.
CAUTION_ZONES: list[dict] = [
    {"latitude": 34.998, "longitude": 68.856, "radius_m": 800,
     "kind": "caution", "message_key": "road.alert.caution"},
]


def _headings(points: list[list[float]]) -> list[float]:
    out = []
    for a, b in zip(points, points[1:]):
        dx = (b[0] - a[0]) * math.cos(math.radians((a[1] + b[1]) / 2))
        out.append(math.degrees(math.atan2(b[1] - a[1], dx)))
    return out


def curve_zones(
    points: list[list[float]],
    *,
    window_m: float = 180.0,
    min_turn_deg: float = 50.0,
    merge_gap_m: float = 400.0,
) -> list[dict]:
    """Where the road bends hard enough to deserve a word.

    Pure geometry over the committed polylines: total heading change inside a
    sliding window. A gentle valley drift never fires; a switchback stack
    fires once, as one zone, because neighbouring hot points merge. Tuned on
    the Ghorband corridor by eye -- the thresholds are data, not physics.
    """
    if len(points) < 3:
        return []
    headings = _headings(points)
    seg_len = [_metres(tuple(a), tuple(b)) for a, b in zip(points, points[1:])]

    hot: list[int] = []
    for i in range(len(headings)):
        turn, span, j = 0.0, 0.0, i
        while j + 1 < len(headings) and span < window_m:
            delta = abs(headings[j + 1] - headings[j])
            turn += min(delta, 360 - delta)
            span += seg_len[j]
            j += 1
        if turn >= min_turn_deg:
            hot.append(i)

    zones: list[dict] = []
    cluster: list[int] = []

    def flush() -> None:
        if not cluster:
            return
        lo, hi = cluster[0], cluster[-1]
        mid = points[(lo + hi) // 2]
        length = sum(seg_len[lo:hi + 1])
        zones.append({
            "latitude": round(mid[1], 5),
            "longitude": round(mid[0], 5),
            "radius_m": int(max(250, length / 2 + 150)),
            "kind": "curve",
            "message_key": "road.alert.curve",
        })
        cluster.clear()

    for i in hot:
        if cluster and sum(seg_len[cluster[-1]:i]) > merge_gap_m:
            flush()
        cluster.append(i)
    flush()
    return zones


@lru_cache(maxsize=1)
def road_alerts() -> list[dict]:
    """Every advisory point on the roads the product drives.

    Computed once from the corridor geometry, plus the hand-placed list.
    Bazaar approaches come from the caller, which knows the stations table.
    """
    seen: list[dict] = list(CAUTION_ZONES)
    for key, leg in _legs().items():
        if not key.startswith(("corridor:", "leg:")):
            continue
        for zone in curve_zones(leg["points"]):
            # The two corridors overlap near Kabul and Charikar; a zone within
            # a kilometre of an already-kept one is the same bend seen twice.
            a = (zone["longitude"], zone["latitude"])
            if all(
                _metres(a, (kept["longitude"], kept["latitude"])) > 1_000
                for kept in seen
            ):
                seen.append(zone)
    return seen


def place(session, table: str, place_id: str | None):
    """Name, coordinates and code of a station or destination row.

    Shared by the driver's trip map and the passenger's journey preview so
    the two views can never disagree about where a place is.
    """
    if place_id is None:
        return None, None
    from sqlalchemy import text as sql

    assert table in ("stations", "destinations")
    row = session.execute(
        sql(f"SELECT name, latitude, longitude, code FROM {table} WHERE id = :id"),
        {"id": place_id},
    ).first()
    if row is None:
        return None, None
    point = None
    if row.latitude is not None and row.longitude is not None:
        point = {
            "name": row.name,
            "latitude": float(row.latitude),
            "longitude": float(row.longitude),
        }
    return point, row.code


def _leg_speed_kmh(leg: dict) -> float | None:
    if not leg.get("duration_s"):
        return None
    return round(leg["distance_m"] / leg["duration_s"] * 3.6, 1)


def journey_line(
    origin_code: str | None,
    dest_code: str | None,
    origin: tuple[float, float] | None,
    dest: tuple[float, float] | None,
) -> dict | None:
    """The road between a trip's two ends.

    Returns {"points": [(lon, lat), ...], "avg_speed_kmh": float | None}. The
    speed is the routing engine's own average for the leg the shape came
    from -- what this road actually does, curves and bazaars amortised --
    which is what an honest "arriving in N minutes" divides by. None means
    "no line": an endpoint with no coordinates, or ends that do not sit on
    any road this file knows.

    An exact precomputed pair wins; otherwise the best corridor slice.
    """
    if origin is None or dest is None:
        return None

    exact = _legs().get(f"pair:{origin_code}:{dest_code}")
    if exact:
        return {"points": exact["points"], "avg_speed_kmh": _leg_speed_kmh(exact)}
    reverse = _legs().get(f"pair:{dest_code}:{origin_code}")
    if reverse:
        return {
            "points": list(reversed(reverse["points"])),
            "avg_speed_kmh": _leg_speed_kmh(reverse),
        }

    best: dict | None = None
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
            best = {
                "points": cut if i <= j else list(reversed(cut)),
                "avg_speed_kmh": _leg_speed_kmh(leg),
            }
            best_score = score
    return best
