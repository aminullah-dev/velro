"""Geography repositories.

The read path here is on the passenger's critical path and runs on a slow
connection, so queries are narrow and bounded.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, or_, select

from domain.enums import GeoStatus
from domain.text import comparison_key
from infrastructure.db.models.geography import (
    DestinationRow,
    DistrictRow,
    ProvinceRow,
    StationRow,
    VillageAliasRow,
    VillageRow,
)
from infrastructure.db.models.routing import RouteRow
from infrastructure.db.repositories.base import SqlRepository
from shared import error_codes

# One degree of latitude is ~111 km everywhere; longitude shrinks with latitude.
# At Ghorband's latitude (~35 deg N) one degree of longitude is ~91 km. Good
# enough to pre-filter a bounding box before sorting precisely.
_M_PER_DEG_LAT = Decimal("111000")
_M_PER_DEG_LON = Decimal("91000")


class GeographyRepository:
    def __init__(self, session) -> None:
        self.session = session

    # -- browse -----------------------------------------------------------

    def list_provinces(self) -> list[ProvinceRow]:
        return list(
            self.session.scalars(
                select(ProvinceRow)
                .where(
                    ProvinceRow.deleted_at.is_(None),
                    ProvinceRow.status == GeoStatus.ACTIVE.value,
                )
                .order_by(ProvinceRow.name)
            ).all()
        )

    def list_districts(self, *, province_id: str | None = None) -> list[DistrictRow]:
        stmt = select(DistrictRow).where(
            DistrictRow.deleted_at.is_(None), DistrictRow.status == GeoStatus.ACTIVE.value
        )
        if province_id:
            stmt = stmt.where(DistrictRow.province_id == province_id)
        return list(self.session.scalars(stmt.order_by(DistrictRow.code)).all())

    def list_villages(
        self, district_id: str, *, limit: int = 200, offset: int = 0
    ) -> list[VillageRow]:
        stmt = (
            select(VillageRow)
            .where(
                VillageRow.district_id == district_id,
                VillageRow.deleted_at.is_(None),
                VillageRow.status == GeoStatus.ACTIVE.value,
            )
            .order_by(VillageRow.name)
            .limit(min(limit, 500))
            .offset(offset)
        )
        return list(self.session.scalars(stmt).all())

    def list_stations(self, village_id: str) -> list[StationRow]:
        stmt = (
            select(StationRow)
            .where(
                StationRow.village_id == village_id,
                StationRow.deleted_at.is_(None),
                StationRow.status == GeoStatus.ACTIVE.value,
            )
            .order_by(StationRow.is_primary.desc(), StationRow.name)
        )
        return list(self.session.scalars(stmt).all())

    def find_station(self, id: str) -> StationRow | None:
        """None when absent. ``get_station`` raises; never mix the two."""
        return self.session.scalars(
            select(StationRow).where(StationRow.id == id, StationRow.deleted_at.is_(None))
        ).one_or_none()

    def get_station(self, id: str) -> StationRow:
        row = self.find_station(id)
        if row is None:
            from shared.errors import NotFoundError

            raise NotFoundError(error_codes.STATION_NOT_FOUND, id=id)
        return row

    def find_destination(self, id: str) -> DestinationRow | None:
        return self.session.scalars(
            select(DestinationRow).where(
                DestinationRow.id == id, DestinationRow.deleted_at.is_(None)
            )
        ).one_or_none()

    def get_destination(self, id: str) -> DestinationRow:
        row = self.find_destination(id)
        if row is None:
            from shared.errors import NotFoundError

            raise NotFoundError(error_codes.DESTINATION_NOT_FOUND, id=id)
        return row

    # -- search -----------------------------------------------------------

    def search_villages(self, term: str, *, limit: int = 20) -> list[VillageRow]:
        """Matches the stored name, the normalised key, and any alias.

        Searching the normalised key is what makes a passenger typing with an
        Arabic yeh find a village stored with a Persian one.
        """
        key = comparison_key(term)
        if not key:
            return []
        pattern = f"%{key}%"
        alias_match = select(VillageAliasRow.village_id).where(
            VillageAliasRow.name_key.like(pattern),
            VillageAliasRow.deleted_at.is_(None),
        )
        stmt = (
            select(VillageRow)
            .where(
                VillageRow.deleted_at.is_(None),
                VillageRow.status == GeoStatus.ACTIVE.value,
                or_(
                    VillageRow.name_key.like(pattern),
                    VillageRow.code.ilike(f"%{term}%"),
                    VillageRow.id.in_(alias_match),
                ),
            )
            .order_by(func.length(VillageRow.name_key), VillageRow.name)
            .limit(min(limit, 50))
        )
        return list(self.session.scalars(stmt).all())

    def aliases_for(self, village_ids) -> dict[str, list[str]]:
        """Every alias for a page of villages, in one query."""
        wanted = [i for i in set(village_ids) if i]
        if not wanted:
            return {}
        rows = self.session.execute(
            select(VillageAliasRow.village_id, VillageAliasRow.name)
            .where(
                VillageAliasRow.village_id.in_(wanted),
                VillageAliasRow.deleted_at.is_(None),
            )
            .order_by(VillageAliasRow.name)
        ).all()
        out: dict[str, list[str]] = {}
        for village_id, name in rows:
            out.setdefault(village_id, []).append(name)
        return out

    def aliases_matching(self, term: str, village_ids) -> dict[str, str]:
        """For each village, the alias that the search term actually matched.

        A passenger who types the name they use locally should be told which
        name that was, or a result under a different heading looks like the
        wrong village. One query for the page, not one per row.
        """
        key = comparison_key(term)
        wanted = [i for i in set(village_ids) if i]
        if not key or not wanted:
            return {}
        rows = self.session.execute(
            select(VillageAliasRow.village_id, VillageAliasRow.name)
            .where(
                VillageAliasRow.village_id.in_(wanted),
                VillageAliasRow.name_key.like(f"%{key}%"),
                VillageAliasRow.deleted_at.is_(None),
            )
        ).all()
        # First match wins: a village with two aliases both matching is rare,
        # and either answers "why is this here".
        out: dict[str, str] = {}
        for village_id, name in rows:
            out.setdefault(village_id, name)
        return out

    def search_stations(self, term: str, *, limit: int = 20) -> list[StationRow]:
        key = comparison_key(term)
        if not key:
            return []
        stmt = (
            select(StationRow)
            .where(
                StationRow.deleted_at.is_(None),
                StationRow.status == GeoStatus.ACTIVE.value,
                StationRow.name_key.like(f"%{key}%"),
            )
            .order_by(func.length(StationRow.name_key))
            .limit(min(limit, 50))
        )
        return list(self.session.scalars(stmt).all())

    # -- nearby -----------------------------------------------------------

    def nearby_stations(
        self, latitude: Decimal, longitude: Decimal, *, radius_m: int = 15000, limit: int = 10
    ) -> list[tuple[StationRow, int]]:
        """Stations near a GPS fix, with an approximate distance in metres.

        A bounding box in SQL, then an exact sort in Python over the handful of
        rows it returns. PostGIS would be better and is not worth a dependency
        for a few thousand stations.
        """
        d_lat = Decimal(radius_m) / _M_PER_DEG_LAT
        d_lon = Decimal(radius_m) / _M_PER_DEG_LON
        stmt = (
            select(StationRow)
            .where(
                StationRow.deleted_at.is_(None),
                StationRow.status == GeoStatus.ACTIVE.value,
                StationRow.latitude.is_not(None),
                StationRow.longitude.is_not(None),
                StationRow.latitude.between(latitude - d_lat, latitude + d_lat),
                StationRow.longitude.between(longitude - d_lon, longitude + d_lon),
            )
            .limit(200)
        )
        candidates = list(self.session.scalars(stmt).all())
        measured = [
            (row, _approx_distance_m(latitude, longitude, row.latitude, row.longitude))
            for row in candidates
        ]
        measured = [pair for pair in measured if pair[1] <= radius_m]
        measured.sort(key=lambda pair: pair[1])
        return measured[:limit]

    # -- destinations -----------------------------------------------------

    def destinations_reachable_from(self, station_id: str) -> list[DestinationRow]:
        """Only what this origin can actually reach.

        Section 16: after choosing an origin, a passenger is shown the
        destinations that exist for it -- never a menu of places no vehicle goes.
        """
        reachable = select(RouteRow.destination_id).where(
            RouteRow.origin_station_id == station_id,
            RouteRow.deleted_at.is_(None),
            RouteRow.status == "ACTIVE",
        )
        stmt = (
            select(DestinationRow)
            .where(
                DestinationRow.deleted_at.is_(None),
                DestinationRow.status == GeoStatus.ACTIVE.value,
                DestinationRow.id.in_(reachable),
            )
            .order_by(DestinationRow.sort_order, DestinationRow.name)
        )
        return list(self.session.scalars(stmt).all())

    def list_destinations(self) -> list[DestinationRow]:
        stmt = (
            select(DestinationRow)
            .where(
                DestinationRow.deleted_at.is_(None),
                DestinationRow.status == GeoStatus.ACTIVE.value,
            )
            .order_by(DestinationRow.sort_order, DestinationRow.name)
        )
        return list(self.session.scalars(stmt).all())

    def aliases_of(self, village_id: str) -> list[VillageAliasRow]:
        return list(
            self.session.scalars(
                select(VillageAliasRow).where(
                    VillageAliasRow.village_id == village_id,
                    VillageAliasRow.deleted_at.is_(None),
                )
            ).all()
        )

    def snapshot_version(self) -> str:
        """A cheap fingerprint of all geography.

        The mobile clients cache the whole hierarchy and re-download only when
        this changes -- geography changes a few times a year, and re-fetching it
        on a 2G connection is the difference between a usable app and a broken
        one.
        """
        newest = self.session.scalar(
            select(func.max(VillageRow.updated_at))
        )
        counts = self.session.scalar(
            select(func.count()).select_from(VillageRow).where(VillageRow.deleted_at.is_(None))
        )
        stations = self.session.scalar(
            select(func.count()).select_from(StationRow).where(StationRow.deleted_at.is_(None))
        )
        stamp = newest.isoformat() if newest else "0"
        return f"{stamp}:{counts}:{stations}"


def _approx_distance_m(lat1: Decimal, lon1: Decimal, lat2: Decimal, lon2: Decimal) -> int:
    """Equirectangular approximation. Accurate to a few metres over a few km,
    which is far finer than the GPS fix it is comparing against."""
    import math

    dlat = float(lat2 - lat1) * float(_M_PER_DEG_LAT)
    dlon = float(lon2 - lon1) * float(_M_PER_DEG_LON)
    return int(math.hypot(dlat, dlon))


class VillageRepository(SqlRepository[VillageRow]):
    model = VillageRow
    not_found_code = error_codes.VILLAGE_NOT_FOUND


class StationRepository(SqlRepository[StationRow]):
    model = StationRow
    not_found_code = error_codes.STATION_NOT_FOUND


class DestinationRepository(SqlRepository[DestinationRow]):
    model = DestinationRow
    not_found_code = error_codes.DESTINATION_NOT_FOUND


class DistrictRepository(SqlRepository[DistrictRow]):
    model = DistrictRow
    not_found_code = error_codes.DISTRICT_NOT_FOUND


class VillageAliasRepository(SqlRepository[VillageAliasRow]):
    """Alternative names, kept as their own records.

    Section 7: an alias is never folded into the village's name, because the
    name people actually use for a place is not ours to overwrite.
    """

    model = VillageAliasRow
    not_found_code = error_codes.VILLAGE_NOT_FOUND
