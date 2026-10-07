from __future__ import annotations

from decimal import Decimal

from pydantic import Field

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
    # The other names this place is known by. Sent with the list so browsing a
    # district finds a village by the name the passenger actually uses, the same
    # way search does -- an alias only findable through search is half a feature.
    alternative_names: list[str] = Field(default_factory=list)
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


class PlaceOut(Schema):
    """A name people gave to a spot. Never says who gave it."""

    id: str
    name: str
    district_id: str
    village_id: str | None = None
    nearest_station_id: str | None = None
    latitude: Decimal
    longitude: Decimal
    #: APPROVED is shown to everyone nearby; PENDING only ever comes back to
    #: the person who just typed it, so the app can say "we will check this".
    status: str
    distance_m: int | None = None


class ResolveOut(Schema):
    """Everything the "my current location" card needs, in one round trip.

    One request rather than three because it is made on a 2G connection by
    somebody standing at the roadside waiting to see whether this works.
    """

    #: Within reach of a station VELRO serves. False is "we don't come here
    #: yet", said before the passenger types anything.
    inside: bool
    district: DistrictOut | None = None
    #: "station" when the nearest placed station decided it, "centre" when only
    #: a district's centre point was near -- a guess the app offers to change.
    district_source: str | None = None
    #: Where a passenger here boards, nearest first.
    stations: list[NearbyStationOut] = Field(default_factory=list)
    #: Approved names within walking distance, nearest first.
    places: list[PlaceOut] = Field(default_factory=list)


class PlaceIn(Schema):
    name: str = Field(max_length=120)
    latitude: Decimal
    longitude: Decimal
    #: The fix's accuracy radius, in metres, as the phone reported it.
    accuracy_m: float | None = Field(default=None, ge=0)
    location_is_mock: bool = False
    #: Only when the passenger corrected the district the fix suggested.
    district_id: str | None = Field(default=None, max_length=36)
