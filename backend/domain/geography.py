"""Geography.

VELRO is a station-based system before it is a GPS system: a passenger who
cannot get an accurate fix must still be able to travel. Coordinates are
therefore optional on every entity here, and nothing in the booking flow
requires them.

Province -> Region -> District -> Village -> Station, with Destination as an
independent entity so that Charikar, Qarabagh and Kabul are rows rather than
constants, and so Kabul can own Khair Khana Mina and Jada as children.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from domain.enums import DestinationKind, GeoStatus
from shared import error_codes
from shared.errors import ValidationError

#: Where a coordinate came from, written into source_note.
#:
#: The distinction is not bookkeeping. A seeded point is a plausible guess
#: made by a developer who has never been there -- the first one an operator
#: checked was fourteen kilometres out -- while an operator's point is the
#: only ground truth this product will ever have. Only the second kind is
#: master data, and only the second kind is exported.
SEED_SOURCE_NOTE = "development seed - not master data"
PLACED_SOURCE_NOTE = "placed by admin on the VELRO map"

_LAT_RANGE = (Decimal("-90"), Decimal("90"))
_LON_RANGE = (Decimal("-180"), Decimal("180"))


@dataclass(frozen=True, slots=True)
class Coordinates:
    latitude: Decimal
    longitude: Decimal

    def __post_init__(self) -> None:
        if isinstance(self.latitude, float) or isinstance(self.longitude, float):
            raise TypeError("coordinates use Decimal; float loses precision on round-trip")
        if not _LAT_RANGE[0] <= self.latitude <= _LAT_RANGE[1]:
            raise ValidationError(error_codes.VALIDATION_FAILED, field="latitude")
        if not _LON_RANGE[0] <= self.longitude <= _LON_RANGE[1]:
            raise ValidationError(error_codes.VALIDATION_FAILED, field="longitude")


@dataclass(slots=True)
class Province:
    id: str
    code: str
    name: str
    country_code: str = "AF"
    status: GeoStatus = GeoStatus.ACTIVE


@dataclass(slots=True)
class Region:
    """A named cluster of districts -- Ghorband is a region of Parwan."""

    id: str
    code: str
    name: str
    province_id: str
    status: GeoStatus = GeoStatus.ACTIVE


@dataclass(slots=True)
class District:
    id: str
    code: str            # GRB-SYG
    name: str
    province_id: str
    region_id: str | None = None
    alternative_name: str | None = None
    coordinates: Coordinates | None = None
    status: GeoStatus = GeoStatus.ACTIVE


@dataclass(slots=True)
class Village:
    id: str
    code: str            # GRB-SYG-001
    name: str
    district_id: str
    coordinates: Coordinates | None = None
    status: GeoStatus = GeoStatus.ACTIVE
    # Alternative names are held as their own records, never merged into `name`.
    aliases: list[str] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        return self.status is GeoStatus.ACTIVE


@dataclass(slots=True)
class Station:
    """A boarding point. A village has at least one, and may have several."""

    id: str
    code: str            # GRB-SYG-001-S1
    name: str
    village_id: str
    district_id: str
    coordinates: Coordinates | None = None
    description: str | None = None
    is_primary: bool = False
    status: GeoStatus = GeoStatus.ACTIVE

    def assert_bookable(self) -> None:
        if self.status is not GeoStatus.ACTIVE:
            raise ValidationError(error_codes.STATION_DISABLED, station_id=self.id)


@dataclass(slots=True)
class Destination:
    """Where a passenger may travel to.

    A destination is deliberately not a station: 'Kabul' is a destination that
    owns 'Khair Khana Mina' and 'Jada' as children, and none of the three is a
    boarding point in Ghorband.
    """

    id: str
    code: str
    name: str
    kind: DestinationKind
    parent_id: str | None = None
    district_id: str | None = None   # set for INTERNAL destinations
    station_id: str | None = None    # set when the destination is a concrete stop
    coordinates: Coordinates | None = None
    sort_order: int = 0
    status: GeoStatus = GeoStatus.ACTIVE

    @property
    def is_group(self) -> bool:
        """A grouping row such as Kabul, chosen only through one of its children."""
        return self.station_id is None and self.district_id is None and self.parent_id is None

    def assert_bookable(self) -> None:
        if self.status is not GeoStatus.ACTIVE:
            raise ValidationError(error_codes.DESTINATION_DISABLED, destination_id=self.id)


def assert_no_cycle(destination_id: str, parent_chain: list[str]) -> None:
    """A destination may not be its own ancestor."""
    if destination_id in parent_chain:
        raise ValidationError(
            error_codes.DESTINATION_CYCLE,
            destination_id=destination_id,
            chain=parent_chain,
        )
