"""Measure the routes against the road, instead of guessing them.

Every route in the database carried a number somebody typed: 25 km and 45
minutes for anything inside Ghorband, whatever the two places actually are.
The operator noticed the way anyone from the valley would -- "دشتک to
سیاه‌گرد is ten kilometres" -- and he is right, and the database was wrong
1,275 times.

It does not have to be typed. He has placed the coordinates, the road
geometry is committed, and mapdata already slices the corridor between any
two points: the distance from دشتک to سیاه‌گرد is the length of that slice.
So this walks every route, draws the line, and writes down how long it is.

    PYTHONPATH=. python scripts/measure-routes.py            # say what it would do
    PYTHONPATH=. python scripts/measure-routes.py --apply

A route whose ends are not both placed keeps whatever it had: this replaces
guesses with measurements, and refuses to replace a guess with a different
guess. Duration comes from the routing engine's own average speed for that
road -- the number the ETA already trusts -- rounded up to the minute.
"""

from __future__ import annotations

import argparse
import math
import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from ui.api import mapdata


def _length_m(points: list[list[float]]) -> float:
    total = 0.0
    for (lon_a, lat_a), (lon_b, lat_b) in zip(points, points[1:]):
        dx = (lon_a - lon_b) * 111_320 * math.cos(math.radians((lat_a + lat_b) / 2))
        dy = (lat_a - lat_b) * 110_574
        total += math.hypot(dx, dy)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the measurements")
    args = parser.parse_args()

    engine = create_engine(os.environ.get(
        "VELRO_DATABASE_URL",
        "postgresql+psycopg://aminullahhashemi@localhost:5432/velro_dev",
    ))
    measured = unmeasurable = unchanged = 0
    with Session(engine) as session:
        rows = session.execute(text(
            "SELECT r.id, r.code, r.distance_m, r.duration_minutes, "
            "       s.code AS origin_code, s.latitude AS o_lat, s.longitude AS o_lon, "
            "       d.code AS dest_code, d.latitude AS d_lat, d.longitude AS d_lon "
            "FROM routes r "
            "JOIN stations s ON s.id = r.origin_station_id "
            "JOIN destinations d ON d.id = r.destination_id "
            "WHERE r.deleted_at IS NULL"
        )).all()

        for row in rows:
            if row.o_lat is None or row.d_lat is None:
                unmeasurable += 1
                continue
            shape = mapdata.journey_line(
                row.origin_code, row.dest_code,
                (float(row.o_lon), float(row.o_lat)),
                (float(row.d_lon), float(row.d_lat)),
            )
            if shape is None:
                unmeasurable += 1
                continue

            metres = round(_length_m(shape["points"]))
            speed = shape["avg_speed_kmh"] or 40.0
            minutes = max(1, math.ceil(metres / 1000 / speed * 60))
            if row.distance_m == metres and row.duration_minutes == minutes:
                unchanged += 1
                continue

            measured += 1
            if measured <= 8:
                was = f"{(row.distance_m or 0)/1000:.0f} km/{row.duration_minutes or 0}m"
                print(f"  {row.code}: {was} -> {metres/1000:.1f} km/{minutes}m")
            if args.apply:
                session.execute(text(
                    "UPDATE routes SET distance_m = :m, duration_minutes = :d, "
                    "version = version + 1 WHERE id = :id"
                ), {"m": metres, "d": minutes, "id": row.id})

        if args.apply:
            session.commit()

    if measured > 8:
        print(f"  ... and {measured - 8} more")
    verb = "measured" if args.apply else "would measure"
    print(f"{verb} {measured}, already right {unchanged}, "
          f"cannot measure {unmeasurable} (an end without coordinates)")
    if not args.apply and measured:
        print("nothing written -- run again with --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
