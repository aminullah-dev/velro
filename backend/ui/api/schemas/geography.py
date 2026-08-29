from __future__ import annotations

from decimal import Decimal

from ui.api.schemas.common import Schema


class DistrictOut(Schema):
    id: str
    code: str
    name: str
    alternative_name: str | None = None
    province_id: str
    latitude: Decimal | None = None
    longitude: Decimal | None = None


class VillageOut(Schema):
    id: str
    code: str
    name: str
    district_id: str
    latitude: Decimal | None = None
    longitude: Decimal | None = None


class StationOut(Schema):
    id: str
    code: str
    name: str
    village_id: str
    district_id: str
    is_primary: bool
    description: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None


class NearbyStationOut(StationOut):
    distance_m: int


class DestinationOut(Schema):
    id: str
    code: str
    name: str
    kind: str
    parent_id: str | None = None
    district_id: str | None = None
    station_id: str | None = None
    sort_order: int


class DestinationGroupOut(Schema):
    """Kabul with Khair Khana Mina and Jada beneath it (section 16)."""

    id: str
    code: str
    name: str
    kind: str
    children: list[DestinationOut]


class GeoSnapshotOut(Schema):
    """The whole hierarchy in one response.

    Geography changes a few times a year. The clients cache this and re-fetch
    only when ``version`` changes, so a passenger on a 2G connection downloads
    it once rather than on every search.
    """

    version: str
    districts: list[DistrictOut]
    villages: list[VillageOut]
    stations: list[StationOut]
    destinations: list[DestinationOut]


class SearchResultOut(Schema):
    kind: str            # village | station
    id: str
    code: str
    name: str
    district_id: str
    village_id: str | None = None
    matched_alias: str | None = None
