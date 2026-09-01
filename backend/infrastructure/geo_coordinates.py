"""The geography as master data, in a file, in git.

Everything else this product knows can be rebuilt: trips regenerate, routes
generate, the map is a download. This cannot. Four hundred and twenty-seven
villages arrived through a single spreadsheet upload whose file was never
kept, and their coordinates exist because one person who has stood in them
pointed at a map, hundreds of times. Both lived in one Postgres database on
one laptop, with no backup and no way to reach a server.

So they live here instead: resources/geo/geography.csv, reviewable in a
diff, restorable from any clone, and carried to production by the same push
that carries the code. A database is a cache of this file.

Coordinates are written down only when an operator placed them. A seeded
guess is already in scripts/seed.py and is not master data; exporting it
would launder a guess into a fact.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from domain.geography import PLACED_SOURCE_NOTE

FILE = Path(__file__).resolve().parent.parent / "resources" / "geo" / "geography.csv"

FIELDS = ("kind", "code", "name", "district_code", "latitude", "longitude")

#: A station further than this from its village is carrying its own point
#: and is exported in its own right; anything closer is just following, and
#: writing it down twice would only create a second place to be wrong.
STATION_EXCEPTION_M = 50


@dataclass(frozen=True)
class Place:
    """One village or one station. Coordinates are optional: most of the
    geography is still unplaced, and a row without them still carries the
    name and the district, which is most of what was lost if this file did
    not exist."""

    kind: str          # "village" | "station"
    code: str
    name: str
    district_code: str
    latitude: Decimal | None
    longitude: Decimal | None

    def row(self) -> dict:
        return {
            "kind": self.kind,
            "code": self.code,
            "name": self.name,
            "district_code": self.district_code,
            "latitude": "" if self.latitude is None else f"{self.latitude:.6f}",
            "longitude": "" if self.longitude is None else f"{self.longitude:.6f}",
        }


def read(path: Path | None = None) -> list[Place]:
    """The file, or nothing. A missing file is a normal state, not an error."""
    target = path or FILE
    if not target.is_file():
        return []
    with target.open(encoding="utf-8", newline="") as handle:
        return [
            Place(
                kind=row["kind"], code=row["code"], name=row["name"],
                district_code=row["district_code"],
                latitude=Decimal(row["latitude"]) if row["latitude"] else None,
                longitude=Decimal(row["longitude"]) if row["longitude"] else None,
            )
            for row in csv.DictReader(handle)
        ]


def write(places: list[Place], path: Path | None = None) -> Path:
    """Villages first, then stations, each sorted by code.

    The order is load-bearing, not cosmetic: a station cannot be created
    before the village that owns it, and "station" sorts before "village"
    alphabetically -- which is exactly how the first rebuild produced four
    hundred villages and twelve stations.
    """
    target = path or FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(places, key=lambda p: (0 if p.kind == "village" else 1, p.code))
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for place in ordered:
            writer.writerow(place.row())
    return target


def gather(session) -> list[Place]:
    """Every village and station in a database, with the district that owns it.

    Coordinates ride along only when an operator placed them. Seeded guesses
    are left blank on purpose: this file is the record of what somebody
    actually knows, and a blank is the honest way to say "nobody has been
    asked yet".
    """
    from sqlalchemy import text as sql

    places: list[Place] = []
    for row in session.execute(sql(
        "SELECT v.code, v.name, d.code AS district_code, v.latitude, v.longitude, "
        "       v.source_note "
        "FROM villages v JOIN districts d ON d.id = v.district_id "
        "WHERE v.deleted_at IS NULL ORDER BY v.code"
    )).all():
        placed = row.source_note == PLACED_SOURCE_NOTE
        places.append(Place(
            "village", row.code, row.name, row.district_code,
            row.latitude if placed else None,
            row.longitude if placed else None,
        ))

    for row in session.execute(sql(
        "SELECT s.code, s.name, d.code AS district_code, s.latitude, s.longitude, "
        "       v.latitude AS v_lat, v.longitude AS v_lon, v.source_note "
        "FROM stations s "
        "JOIN villages v ON v.id = s.village_id "
        "JOIN districts d ON d.id = s.district_id "
        "WHERE s.deleted_at IS NULL ORDER BY s.code"
    )).all():
        # A station that merely stands with its village needs no coordinates
        # of its own: importing the village puts it there. Only a station
        # somebody moved away carries its own point.
        own_point = None
        if (
            row.source_note == PLACED_SOURCE_NOTE
            and s_has_point(row)
            and _metres((row.latitude, row.longitude), (row.v_lat, row.v_lon))
            > STATION_EXCEPTION_M
        ):
            own_point = (row.latitude, row.longitude)
        places.append(Place(
            "station", row.code, row.name, row.district_code,
            own_point[0] if own_point else None,
            own_point[1] if own_point else None,
        ))
    return places


def s_has_point(row) -> bool:
    return (
        row.latitude is not None and row.v_lat is not None
    )


@dataclass
class Applied:
    created: list[str]
    placed: list[str]
    corrected: list[str]
    unchanged: list[str]
    #: (code, why) for rows that could not land at all.
    skipped: list[tuple[str, str]]

    def summary(self) -> str:
        return (
            f"{len(self.created)} created, {len(self.placed)} placed, "
            f"{len(self.corrected)} corrected, {len(self.unchanged)} already right, "
            f"{len(self.skipped)} skipped"
        )


def apply(session, places: list[Place]) -> Applied:
    """Put the file into a database. Idempotent, and loud about surprises.

    Creates what is missing -- the four hundred villages arrived through a
    spreadsheet nobody kept, so "missing" is the normal state of any
    database but the one they were typed into -- and moves what has been
    corrected. A row whose district does not exist is reported rather than
    invented: districts are seeded, and one that is absent means this file
    and the seed have drifted, which somebody must look at before a trip is
    sold along a road that does not exist.
    """
    from sqlalchemy import text as sql

    from domain.text import comparison_key
    from shared.ids import new_id

    result = Applied([], [], [], [], [])
    districts = {
        row.code: row.id
        for row in session.execute(sql(
            "SELECT id, code FROM districts WHERE deleted_at IS NULL"
        )).all()
    }
    villages_by_code: dict[str, str] = {}

    for place in places:
        table = "villages" if place.kind == "village" else "stations"
        row = session.execute(
            sql(f"SELECT id, latitude, longitude FROM {table} "
                f"WHERE code = :code AND deleted_at IS NULL"),
            {"code": place.code},
        ).first()

        if row is None:
            district_id = districts.get(place.district_code)
            if district_id is None:
                result.skipped.append((place.code, f"no district {place.district_code}"))
                continue
            new = _create(
                session, sql, place, district_id, villages_by_code,
                comparison_key, new_id,
            )
            if new is None:
                result.skipped.append((place.code, "its village is not in the file"))
                continue
            result.created.append(place.code)
            # No early exit for a row without coordinates: a station that
            # has just been created is exactly the one that still has to
            # inherit its village's point, and the block below is where
            # that happens.
            row_id, current = new, None
        else:
            row_id, current = row.id, (row.latitude, row.longitude)
            if place.kind == "village":
                villages_by_code[place.code] = row.id

        if place.latitude is None:
            # A station carries no point of its own in the file when it
            # simply stands with its village -- so it inherits, here, at the
            # moment it exists. Doing it when the village was placed does not
            # work on a fresh database: villages are written first precisely
            # because a station cannot be created before the village that
            # owns it, which means the station is not there yet to follow.
            # Four hundred and fifteen stations arrived on production with no
            # coordinates for exactly this reason, and the export could not
            # see it, because a station that agrees with its village is
            # recorded as a blank either way.
            if place.kind == "station":
                session.execute(
                    sql("UPDATE stations s SET latitude = v.latitude, "
                        "  longitude = v.longitude, version = s.version + 1 "
                        "FROM villages v "
                        "WHERE s.village_id = v.id AND s.id = :id "
                        "  AND s.latitude IS NULL AND v.latitude IS NOT NULL"),
                    {"id": row_id},
                )
            continue          # the file says nobody has placed this one
        if current and current[0] is not None and _metres(
            current, (place.latitude, place.longitude)
        ) <= 1:
            result.unchanged.append(place.code)
            continue

        session.execute(
            sql(f"UPDATE {table} SET latitude = :lat, longitude = :lon, "
                f"version = version + 1 WHERE id = :id"),
            {"lat": place.latitude, "lon": place.longitude, "id": row_id},
        )
        if place.kind == "village":
            session.execute(
                sql("UPDATE villages SET source_note = :note WHERE id = :id"),
                {"note": PLACED_SOURCE_NOTE, "id": row_id},
            )
            # Stations follow their village on exactly the placer's rule: one
            # standing with it moves, one holding its own point is left for
            # its own row in this file to set.
            previous = current if current and current[0] is not None else None
            session.execute(
                sql("UPDATE stations SET latitude = :lat, longitude = :lon, "
                    "version = version + 1 "
                    "WHERE village_id = :vid AND deleted_at IS NULL "
                    "AND (latitude IS NULL OR ("
                    "  abs(latitude - :prev_lat) < 0.01 AND"
                    "  abs(longitude - :prev_lon) < 0.01))"),
                {
                    "lat": place.latitude, "lon": place.longitude, "vid": row_id,
                    "prev_lat": previous[0] if previous else place.latitude,
                    "prev_lon": previous[1] if previous else place.longitude,
                },
            )
        if current and current[0] is not None:
            result.corrected.append(place.code)
        else:
            result.placed.append(place.code)
    return result


def _create(session, sql, place: Place, district_id: str, villages_by_code,
            comparison_key, new_id) -> str | None:
    """Bring back a village or station the database has never had."""
    ident = new_id()
    if place.kind == "village":
        session.execute(sql(
            "INSERT INTO villages (id, code, name, name_key, district_id, status, "
            "  latitude, longitude, source_note, version, created_at, updated_at) "
            "VALUES (:id, :code, :name, :key, :district, 'ACTIVE', NULL, NULL, "
            "  NULL, 1, now(), now())"
        ), {
            "id": ident, "code": place.code, "name": place.name,
            "key": comparison_key(place.name), "district": district_id,
        })
        villages_by_code[place.code] = ident
        return ident

    # A station belongs to the village whose code prefixes its own.
    village_code = place.code.rsplit("-S", 1)[0]
    village_id = villages_by_code.get(village_code)
    if village_id is None:
        found = session.execute(
            sql("SELECT id FROM villages WHERE code = :code AND deleted_at IS NULL"),
            {"code": village_code},
        ).first()
        if found is None:
            return None
        village_id = found.id
        villages_by_code[village_code] = village_id
    session.execute(sql(
        "INSERT INTO stations (id, code, name, name_key, village_id, district_id, "
        "  is_primary, status, latitude, longitude, version, created_at, updated_at) "
        "VALUES (:id, :code, :name, :key, :village, :district, true, 'ACTIVE', "
        "  NULL, NULL, 1, now(), now())"
    ), {
        "id": ident, "code": place.code, "name": place.name,
        "key": comparison_key(place.name), "village": village_id,
        "district": district_id,
    })
    return ident


def _metres(a, b) -> float:
    import math

    lat_a, lon_a = float(a[0]), float(a[1])
    lat_b, lon_b = float(b[0]), float(b[1])
    dx = (lon_a - lon_b) * 111_320 * math.cos(math.radians((lat_a + lat_b) / 2))
    dy = (lat_a - lat_b) * 110_574
    return math.hypot(dx, dy)
