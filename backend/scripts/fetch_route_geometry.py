"""Fetch the region's road geometry, once, at a developer's desk.

VELRO's routes are fixed lines between fixed stations, so the shape of every
journey is static data, not a runtime question. This script asks OSRM's public
demo server for that shape a handful of times and writes the answers into
resources/map/geometry.json, which is committed. Production never calls a
routing engine; it reads a file.

Run it again only when the geography grows -- a new corridor, a new external
destination. It is polite to the demo server (one request per second), which
is the correct price for using a shared community machine.

Usage: PYTHONPATH=. .venv/bin/python scripts/fetch_route_geometry.py
Needs VELRO_DATABASE_URL (or the dev default) for the station/destination
coordinates; writes resources/map/geometry.json.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text

OSRM = "https://router.project-osrm.org/route/v1/driving"
OUT = Path(__file__).resolve().parent.parent / "resources" / "map" / "geometry.json"

#: The two valleys and the city spur. Each corridor is one OSRM call from its
#: far end to Kabul's جاده station; the road it returns passes every station
#: that lies along it, which is what makes it reusable for any trip on it.
CORRIDORS = [
    # درهٔ غوربند: from the valley's deepest coord'd station down to Kabul.
    ("corridor:ghorband", "GRB-SYG-003-S1", "KBL-JAD-001-S1"),
    # درهٔ شیخ‌علی / سرخ‌پارسا: the parallel southern road.
    ("corridor:sheikh-ali", "GRB-SPA-002-S1", "KBL-JAD-001-S1"),
]

#: Kabul's second station and the northern spur, so a قره‌باغ or خیرخانه
#: journey has its own shape too.
EXTRA_LEGS = [
    ("leg:charikar-qarabagh", ("EXT-CHK",), ("EXT-QRB",)),
    ("leg:charikar-khairkhana", ("EXT-CHK",), ("KBL-KHM-001-S1",)),
]


def _coords(session) -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    for code, lat, lon in session.execute(text(
        "SELECT code, latitude, longitude FROM stations "
        "WHERE latitude IS NOT NULL AND deleted_at IS NULL"
    )):
        out[code] = (float(lon), float(lat))
    for code, lat, lon in session.execute(text(
        "SELECT code, latitude, longitude FROM destinations "
        "WHERE latitude IS NOT NULL AND deleted_at IS NULL"
    )):
        out[code] = (float(lon), float(lat))
    return out


def _trip_pairs(session) -> list[tuple[str, str]]:
    return [
        (s, d)
        for s, d in session.execute(text(
            "SELECT DISTINCT st.code, de.code FROM trips t "
            "JOIN stations st ON st.id = t.origin_station_id "
            "JOIN destinations de ON de.id = t.destination_id"
        ))
    ]


def _route(client: httpx.Client, a: tuple[float, float], b: tuple[float, float]) -> dict | None:
    url = f"{OSRM}/{a[0]},{a[1]};{b[0]},{b[1]}?overview=full&geometries=geojson"
    reply = client.get(url, timeout=30)
    reply.raise_for_status()
    body = reply.json()
    if body.get("code") != "Ok" or not body.get("routes"):
        return None
    route = body["routes"][0]
    return {
        "distance_m": round(route["distance"]),
        "duration_s": round(route["duration"]),
        # The coordinates this shape was asked about. A station's point can
        # be corrected later -- the first operator session moved one
        # fourteen kilometres -- and a precomputed line drawn from the old
        # one is a lie the reader must be able to detect. mapdata compares
        # these against the live coordinates and ignores a leg that has
        # drifted.
        "from_lonlat": [round(a[0], 5), round(a[1], 5)],
        "to_lonlat": [round(b[0], 5), round(b[1], 5)],
        # (lon, lat) pairs, rounded to ~1 m so the file stays honest and small.
        "points": [[round(lon, 5), round(lat, 5)] for lon, lat in route["geometry"]["coordinates"]],
    }


def main() -> None:
    url = os.environ.get(
        "VELRO_DATABASE_URL",
        "postgresql+psycopg://aminullahhashemi@localhost:5432/velro_dev",
    )
    engine = create_engine(url)
    legs: dict[str, dict] = {}
    with engine.connect() as session, httpx.Client(
        headers={"User-Agent": "velro-geometry-fetch (one-off, dev)"}
    ) as client:
        coords = _coords(session)

        wanted: list[tuple[str, str, str]] = []
        for key, a, b in CORRIDORS:
            wanted.append((key, a, b))
        for key, (a,), (b,) in EXTRA_LEGS:
            wanted.append((key, a, b))
        for s, d in _trip_pairs(session):
            wanted.append((f"pair:{s}:{d}", s, d))

        for key, a_code, b_code in wanted:
            a, b = coords.get(a_code), coords.get(b_code)
            if a is None or b is None:
                print(f"skip {key}: no coordinates for {a_code if a is None else b_code}")
                continue
            leg = _route(client, a, b)
            if leg is None:
                print(f"skip {key}: OSRM found no road")
                continue
            leg["from"] = a_code
            leg["to"] = b_code
            legs[key] = leg
            print(f"ok   {key}: {leg['distance_m']/1000:.1f} km, {len(leg['points'])} points")
            time.sleep(1)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"version": 1, "legs": legs}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"wrote {OUT} ({OUT.stat().st_size/1024:.0f} KiB, {len(legs)} legs)")


if __name__ == "__main__":
    main()
