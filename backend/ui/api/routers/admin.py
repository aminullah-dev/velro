"""Admin: the dashboard, operations lists and finance.

Read-heavy. Everything here is scoped by a role dependency rather than by a
check inside a handler, and every state change writes an audit entry inside the
same transaction as the change.

Aggregates are computed in the database rather than by fetching rows and
counting them in Python -- these are the queries most likely to be written once
and never profiled, and the tables they read grow fastest.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from application.use_cases.generate_routes import (
    GenerateRoutes,
    GenerateRoutesCommand,
)
from application.use_cases.record_name import RecordName, RecordNameCommand
from domain.enums import (
    Locale,
    TripStatus,
    UserStatus,
    VehicleStatus,
)
from domain.geography import PLACED_SOURCE_NOTE, SEED_SOURCE_NOTE
from domain.identity import DRIVER as DRIVER_ROLE
from domain.identity import PhoneNumber
from domain.identity import User as DomainUser
from infrastructure.db.models.geography import (
    DestinationRow,
    DistrictRow,
    StationRow,
    VillageRow,
)
from infrastructure.db.models.identity import UserRow
from infrastructure.db.models.money import CommissionRow, PaymentRow
from infrastructure.db.models.ops import AuditLogRow, SettingRow
from infrastructure.db.models.routing import FareRuleRow, RouteRow
from infrastructure.db.models.supply import DriverRow, VehicleRow
from infrastructure.db.models.trips import BookingRow, TripRow
from shared import error_codes
from shared.errors import ConflictError, NotFoundError, ValidationError
from ui.api import deps, opscentre
from ui.api.errors import ok
from ui.api.schemas.common import Schema


class GenerateRoutesIn(Schema):
    # Absent regenerates every active template, which is what a fresh import
    # needs; naming one is for re-running a single corrected template.
    template_id: str | None = None


router = APIRouter(prefix="/admin", tags=["admin"])

# A "day" is a business day in the product's timezone, not date() in UTC.
KABUL = ZoneInfo("Asia/Kabul")

_ACTIVE_TRIP_STATUSES = (
    TripStatus.DRIVER_ASSIGNED.value, TripStatus.DRIVER_ARRIVING.value,
    TripStatus.ARRIVED_AT_PICKUP.value, TripStatus.BOARDING.value,
    TripStatus.IN_TRANSIT.value, TripStatus.ARRIVED.value,
)


# -- dashboard -----------------------------------------------------------

@router.get("/dashboard")
def dashboard(
    actor: Annotated[deps.Actor, Depends(deps.require_staff)],
    session: deps.SessionDep,
    settings: Annotated[object, Depends(deps.app_settings)],
) -> dict:
    """Section 47: one screen an operator can read in ten seconds.

    Not a row of counters. What is happening now, what needs somebody, what
    is about to go wrong, and how today went -- see ui/api/opscentre.py,
    which also owns the clauses the filtered lists below share, so a number
    on a card and the rows behind it are one definition.
    """
    return ok(opscentre.snapshot(session, settings, deps.clock().now()))


# -- locations -----------------------------------------------------------

class DistrictAdminOut(Schema):
    id: str
    code: str
    name: str
    alternative_name: str | None
    status: str
    village_count: int
    station_count: int
    #: The district centre, for the placer map to fly to.
    latitude: float | None = None
    longitude: float | None = None


@router.post("/routes/generate")
def generate_routes(
    body: GenerateRoutesIn,
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    templates: Annotated[object, Depends(deps.route_templates)],
    routes: Annotated[object, Depends(deps.routes)],
    route_stops: Annotated[object, Depends(deps.route_stops)],
    geo: Annotated[object, Depends(deps.geography)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    """Materialise routes for every station a template covers, section 12.

    Needed after a village import: the importer creates villages and stations,
    and without this they have no routes -- a station nobody can travel from is
    not on the network, whatever the map says. Regenerating is safe: an existing
    route for a (template, station) pair is updated, not duplicated.
    """
    use_case = GenerateRoutes(
        templates=templates, routes=routes, route_stops=route_stops,
        geography=geo, audit=audit, clock=deps.clock(), new_id=deps.new_id,
    )
    result = use_case.execute(
        GenerateRoutesCommand(
            template_id=body.template_id,
            actor_id=actor.user_id,
            actor_role=actor.role,
        )
    )
    return ok(asdict(result))


@router.get("/districts")
def districts(
    actor: Annotated[deps.Actor, Depends(deps.require_staff)],
    session: deps.SessionDep,
) -> dict:
    """Districts with their counts, in one query rather than one per row."""
    villages = (
        select(VillageRow.district_id, func.count().label("n"))
        .where(VillageRow.deleted_at.is_(None))
        .group_by(VillageRow.district_id)
        .subquery()
    )
    stations = (
        select(StationRow.district_id, func.count().label("n"))
        .where(StationRow.deleted_at.is_(None))
        .group_by(StationRow.district_id)
        .subquery()
    )
    stmt = (
        select(
            DistrictRow,
            func.coalesce(villages.c.n, 0),
            func.coalesce(stations.c.n, 0),
        )
        .outerjoin(villages, villages.c.district_id == DistrictRow.id)
        .outerjoin(stations, stations.c.district_id == DistrictRow.id)
        .where(DistrictRow.deleted_at.is_(None))
        .order_by(DistrictRow.code)
    )
    return ok(
        [
            DistrictAdminOut(
                id=row.id, code=row.code, name=row.name,
                alternative_name=row.alternative_name, status=row.status,
                village_count=int(village_count), station_count=int(station_count),
                latitude=float(row.latitude) if row.latitude is not None else None,
                longitude=float(row.longitude) if row.longitude is not None else None,
            ).model_dump()
            for row, village_count, station_count in session.execute(stmt).all()
        ]
    )


class VillageAdminOut(Schema):
    id: str
    code: str
    name: str
    district_id: str
    district_name: str
    status: str
    latitude: float | None
    longitude: float | None
    station_count: int
    #: True when the only coordinates this village has are the seed's guess.
    #: Placed and unplaced are not the whole truth: a guess looks placed and
    #: is not.
    from_seed: bool = False


@router.get("/villages")
def villages(
    actor: Annotated[deps.Actor, Depends(deps.require_staff)],
    session: deps.SessionDep,
    district_id: str | None = None,
    q: Annotated[str | None, Query(max_length=80)] = None,
    #: The dashboard's network cards: villages the map cannot place, and
    #: villages nobody can travel from.
    without: Annotated[str | None, Query(pattern=r"^(coordinates|stations)$")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    stations = (
        select(StationRow.village_id, func.count().label("n"))
        .where(StationRow.deleted_at.is_(None))
        .group_by(StationRow.village_id)
        .subquery()
    )
    stmt = (
        select(VillageRow, DistrictRow.name, func.coalesce(stations.c.n, 0))
        .join(DistrictRow, DistrictRow.id == VillageRow.district_id)
        .outerjoin(stations, stations.c.village_id == VillageRow.id)
        .where(VillageRow.deleted_at.is_(None))
        .order_by(VillageRow.code)
    )
    if district_id:
        stmt = stmt.where(VillageRow.district_id == district_id)
    if q:
        from domain.text import comparison_key

        stmt = stmt.where(VillageRow.name_key.like(f"%{comparison_key(q)}%"))
    if without == "coordinates":
        stmt = stmt.where(VillageRow.latitude.is_(None))
    elif without == "stations":
        stmt = stmt.where(func.coalesce(stations.c.n, 0) == 0)

    total = session.scalar(
        select(func.count()).select_from(stmt.subquery())
    )
    rows = session.execute(stmt.limit(limit).offset(offset)).all()
    return ok(
        [
            VillageAdminOut(
                id=v.id, code=v.code, name=v.name, district_id=v.district_id,
                district_name=district_name, status=v.status,
                latitude=float(v.latitude) if v.latitude is not None else None,
                longitude=float(v.longitude) if v.longitude is not None else None,
                station_count=int(station_count),
                from_seed=v.source_note == SEED_SOURCE_NOTE,
            ).model_dump()
            for v, district_name, station_count in rows
        ],
        meta={"total": int(total or 0), "limit": limit, "offset": offset},
    )


def _metres(a: tuple, b: tuple) -> float:
    """Equirectangular metres. Exact enough to ask "is this the same spot"."""
    import math

    lat_a, lon_a = float(a[0]), float(a[1])
    lat_b, lon_b = float(b[0]), float(b[1])
    dx = (lon_a - lon_b) * 111_320 * math.cos(math.radians((lat_a + lat_b) / 2))
    dy = (lat_a - lat_b) * 110_574
    return math.hypot(dx, dy)


#: A station further than this from where its village stood was put there
#: deliberately, and a correction to the village does not drag it along.
STATION_FOLLOWS_WITHIN_M = 1_000

# The provenance vocabulary lives in the domain: two scripts and this
# router all have to agree on what a coordinate's origin means.


def station_follows(
    station_at: tuple | None, village_was_at: tuple | None
) -> bool:
    """Does this station move when its village is corrected?

    A station with no point of its own always takes the village's. One that
    was standing with the village follows it. One standing somewhere else --
    which nothing can produce today, and which a future station-level tool
    would -- stays where it was put.
    """
    if station_at is None or station_at[0] is None:
        return True
    if village_was_at is None:
        return False
    return _metres(station_at, village_was_at) <= STATION_FOLLOWS_WITHIN_M


class VillageCoordinatesIn(Schema):
    """Both present to place, both null to clear. Half a coordinate is a typo."""

    latitude: Decimal | None = None
    longitude: Decimal | None = None


@router.patch("/villages/{village_id}/coordinates")
def place_village(
    village_id: str,
    body: VillageCoordinatesIn,
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    session: deps.SessionDep,
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    """The operator's pin on the map, applied to a village and its stations.

    This is how the 415 villages the public map has never heard of get their
    coordinates: someone who has actually stood in them taps the road on the
    product's own map.

    A station follows its village when it was standing with it -- which is
    every station today, since the seed created each one at its village's
    coordinates and nothing else can move one. The first correction proved
    why that matters: خیشکی's seeded point was a sample, the operator moved
    the village fourteen kilometres to where it actually is, and the station
    stayed behind on the old spot -- and the station is what the geofence,
    the journey line and the ETA all read. So "the station keeps its own
    point" now means what it was meant to mean: a point somebody put
    somewhere else on purpose, more than a kilometre from where the village
    stood, is left alone. Everything else moves with the village.

    Clearing reverses exactly that: the village and all its stations forget,
    because a wrong point that has spread is worse than no point.

    The bounds check is the region box with a margin: a mis-tap in the
    Arabian Sea should fail loudly at the moment the operator can still see
    which village they were holding.
    """
    if (body.latitude is None) != (body.longitude is None):
        raise ValidationError(
            error_codes.VALIDATION_FAILED, reason="half_a_coordinate"
        )
    if body.latitude is not None and not (
        Decimal("34.0") <= body.latitude <= Decimal("36.0")
        and Decimal("67.5") <= body.longitude <= Decimal("70.0")
    ):
        raise ValidationError(
            error_codes.VALIDATION_FAILED, reason="outside_region",
            latitude=str(body.latitude), longitude=str(body.longitude),
        )

    village = session.scalars(
        select(VillageRow).where(
            VillageRow.id == village_id, VillageRow.deleted_at.is_(None)
        )
    ).one_or_none()
    if village is None:
        raise NotFoundError(error_codes.VILLAGE_NOT_FOUND, village_id=village_id)

    before = {
        "latitude": str(village.latitude) if village.latitude is not None else None,
        "longitude": str(village.longitude) if village.longitude is not None else None,
    }
    village.latitude = body.latitude
    village.longitude = body.longitude
    village.source_note = (
        PLACED_SOURCE_NOTE if body.latitude is not None else None
    )
    village.version += 1

    stations = session.scalars(
        select(StationRow).where(
            StationRow.village_id == village_id, StationRow.deleted_at.is_(None)
        )
    ).all()
    was_at = None
    if before["latitude"] is not None:
        was_at = (Decimal(before["latitude"]), Decimal(before["longitude"]))

    touched = []
    for station in stations:
        if body.latitude is None:
            if station.latitude is not None:
                station.latitude = None
                station.longitude = None
                touched.append(station.code)
            continue
        if station_follows((station.latitude, station.longitude), was_at):
            station.latitude = body.latitude
            station.longitude = body.longitude
            touched.append(station.code)

    audit.write(
        "village.coordinates",
        actor_id=actor.user_id,
        actor_role=actor.role,
        entity_type="village",
        entity_id=village_id,
        before=before,
        after={
            "latitude": str(body.latitude) if body.latitude is not None else None,
            "longitude": str(body.longitude) if body.longitude is not None else None,
            "stations": touched,
        },
    )
    return ok({
        "village_id": village_id,
        "latitude": float(body.latitude) if body.latitude is not None else None,
        "longitude": float(body.longitude) if body.longitude is not None else None,
        "stations_updated": touched,
    })



class StationAdminOut(Schema):
    id: str
    code: str
    name: str
    village_id: str
    village_name: str
    district_name: str
    is_primary: bool
    status: str
    #: Where the station actually is -- the point the geofence, the journey
    #: line and the ETA all read. Absent from this listing until a placement
    #: correction had to be verified and there was no way to look.
    latitude: float | None = None
    longitude: float | None = None


@router.get("/stations")
def stations(
    actor: Annotated[deps.Actor, Depends(deps.require_staff)],
    session: deps.SessionDep,
    village_id: str | None = None,
    q: Annotated[str | None, Query(max_length=80)] = None,
    #: Stations no active route leaves from: on the map, off the network.
    without_routes: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """Stations, filtered, with the total so a page knows it is a page.

    The search is not decoration: there are 427 of them and this listing
    pages at a hundred, so without it the only way to find one is to know
    its village's id -- which is how three tests came to be quietly reading
    the wrong hundred rows.
    """
    stmt = (
        select(StationRow, VillageRow.name, DistrictRow.name)
        .join(VillageRow, VillageRow.id == StationRow.village_id)
        .join(DistrictRow, DistrictRow.id == StationRow.district_id)
        .where(StationRow.deleted_at.is_(None))
        .order_by(StationRow.code)
    )
    if village_id:
        stmt = stmt.where(StationRow.village_id == village_id)
    if q:
        from domain.text import comparison_key

        needle = comparison_key(q)
        stmt = stmt.where(
            or_(StationRow.name_key.like(f"%{needle}%"), StationRow.code.like(f"%{q}%"))
        )
    if without_routes:
        from sqlalchemy import exists

        from domain.enums import RouteStatus

        stmt = stmt.where(
            ~exists(
                select(RouteRow.id).where(
                    RouteRow.origin_station_id == StationRow.id,
                    RouteRow.status == RouteStatus.ACTIVE.value,
                    RouteRow.deleted_at.is_(None),
                )
            )
        )
    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = session.execute(stmt.limit(limit).offset(offset)).all()
    return ok(
        [
            StationAdminOut(
                id=s.id, code=s.code, name=s.name, village_id=s.village_id,
                village_name=village_name, district_name=district_name,
                is_primary=s.is_primary, status=s.status,
                latitude=float(s.latitude) if s.latitude is not None else None,
                longitude=float(s.longitude) if s.longitude is not None else None,
            ).model_dump()
            for s, village_name, district_name in rows
        ],
        meta={"total": int(total or 0), "limit": limit, "offset": offset},
    )


class DestinationAdminOut(Schema):
    id: str
    code: str
    name: str
    kind: str
    parent_id: str | None
    parent_name: str | None
    sort_order: int
    status: str


@router.get("/destinations")
def destinations(
    actor: Annotated[deps.Actor, Depends(deps.require_staff)],
    session: deps.SessionDep,
) -> dict:
    parent = DestinationRow.__table__.alias("parent")
    stmt = (
        select(DestinationRow, parent.c.name)
        .outerjoin(parent, parent.c.id == DestinationRow.parent_id)
        .where(DestinationRow.deleted_at.is_(None))
        .order_by(DestinationRow.sort_order, DestinationRow.name)
    )
    return ok(
        [
            DestinationAdminOut(
                id=d.id, code=d.code, name=d.name, kind=d.kind,
                parent_id=d.parent_id, parent_name=parent_name,
                sort_order=d.sort_order, status=d.status,
            ).model_dump()
            for d, parent_name in session.execute(stmt).all()
        ]
    )


# -- routes and pricing --------------------------------------------------

class RouteAdminOut(Schema):
    id: str
    code: str
    route_type: str
    origin_station_name: str
    destination_name: str
    distance_m: int | None
    duration_minutes: int | None
    status: str
    fare_minor: int | None
    fare_currency: str | None


@router.get("/routes")
def routes(
    actor: Annotated[deps.Actor, Depends(deps.require_staff)],
    session: deps.SessionDep,
    q: Annotated[str | None, Query(max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """Routes with the shared-ride fare in force today.

    The fare is joined rather than fetched per row: this list is the first place
    an N+1 would show, because there are as many routes as stations times
    destinations.
    """
    today = deps.clock().now().date()
    # The rule in force today, per route.
    #
    # Superseding a price closes the old row and opens a new one, so both exist
    # and only the open one counts -- without the valid_to test a raised price
    # never appears here, and an operator changes it again and again.
    #
    # DISTINCT ON rather than an aggregate: MIN(amount) would return the
    # cheapest matching rule rather than the current one, and aggregating the
    # amount and the currency separately can pair a figure from one row with a
    # currency from another.
    fares = (
        select(
            FareRuleRow.route_id,
            FareRuleRow.amount_minor.label("amount_minor"),
            FareRuleRow.amount_currency.label("currency"),
        )
        .where(
            FareRuleRow.deleted_at.is_(None),
            FareRuleRow.ride_kind == "SHARED",
            FareRuleRow.valid_from <= today,
            or_(FareRuleRow.valid_to.is_(None), FareRuleRow.valid_to >= today),
        )
        .distinct(FareRuleRow.route_id)
        # Newest first, so two rules open on the same day resolve to the one
        # entered last rather than to whichever the planner happened to read.
        .order_by(
            FareRuleRow.route_id,
            FareRuleRow.valid_from.desc(),
            FareRuleRow.created_at.desc(),
        )
        .subquery()
    )
    stmt = (
        select(
            RouteRow, StationRow.name, DestinationRow.name,
            fares.c.amount_minor, fares.c.currency,
        )
        .join(StationRow, StationRow.id == RouteRow.origin_station_id)
        .join(DestinationRow, DestinationRow.id == RouteRow.destination_id)
        .outerjoin(fares, fares.c.route_id == RouteRow.id)
        .where(RouteRow.deleted_at.is_(None))
        .order_by(RouteRow.code)
    )
    if q:
        stmt = stmt.where(RouteRow.code.ilike(f"%{q}%"))

    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = session.execute(stmt.limit(limit).offset(offset)).all()
    return ok(
        [
            RouteAdminOut(
                id=r.id, code=r.code, route_type=r.route_type,
                origin_station_name=origin, destination_name=destination,
                distance_m=r.distance_m, duration_minutes=r.duration_minutes,
                status=r.status,
                fare_minor=int(fare) if fare is not None else None,
                fare_currency=currency,
            ).model_dump()
            for r, origin, destination, fare, currency in rows
        ],
        meta={"total": int(total or 0), "limit": limit, "offset": offset},
    )


class UpdateFareIn(Schema):
    amount_minor: int
    ride_kind: str = "SHARED"
    note: str | None = None


class RouteMeasurementIn(Schema):
    """Both optional, so one can be corrected without restating the other."""

    distance_m: int | None = Field(default=None, ge=100, le=1_000_000)
    duration_minutes: int | None = Field(default=None, ge=1, le=1_440)


@router.patch("/routes/{route_id}")
def correct_route(
    route_id: str,
    body: RouteMeasurementIn,
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    session: deps.SessionDep,
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    """How far it really is, when somebody knows better than the map.

    scripts/measure-routes.py walks the committed road geometry and writes
    down the length of every journey whose two ends have coordinates -- which
    is the honest number and needs no typing. This is for the rest: a route
    with an unplaced end still carrying whatever the seed guessed, or a road
    the geometry describes wrongly because it was rebuilt, or a stretch that
    is closed in winter and genuinely longer.

    Audited like every other correction, because "why does it say 47 km" is
    a question somebody will ask months from now.
    """
    row = session.scalars(
        select(RouteRow).where(RouteRow.id == route_id, RouteRow.deleted_at.is_(None))
    ).one_or_none()
    if row is None:
        raise NotFoundError(error_codes.ROUTE_NOT_FOUND, route_id=route_id)
    if body.distance_m is None and body.duration_minutes is None:
        raise ValidationError(error_codes.VALIDATION_FAILED, reason="nothing_to_change")

    before = {"distance_m": row.distance_m, "duration_minutes": row.duration_minutes}
    if body.distance_m is not None:
        row.distance_m = body.distance_m
    if body.duration_minutes is not None:
        row.duration_minutes = body.duration_minutes
    row.version += 1

    audit.write(
        "route.measured",
        actor_id=actor.user_id,
        actor_role=actor.role,
        entity_type="route",
        entity_id=route_id,
        before=before,
        after={"distance_m": row.distance_m, "duration_minutes": row.duration_minutes},
    )
    return ok({
        "route_id": route_id,
        "distance_m": row.distance_m,
        "duration_minutes": row.duration_minutes,
    })


@router.post("/routes/{route_id}/fare")
def set_route_fare(
    route_id: str,
    body: UpdateFareIn,
    actor: Annotated[deps.Actor, Depends(deps.require_finance)],
    session: deps.SessionDep,
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    """Supersede a price rather than edit one.

    The old rule is closed with ``valid_to`` and a new one inserted, so a
    booking made yesterday can still be explained and the price history stays
    intact (section 29).
    """
    if body.amount_minor < 0:
        raise ConflictError(error_codes.FARE_NEGATIVE, amount_minor=body.amount_minor)

    route = session.scalars(
        select(RouteRow).where(RouteRow.id == route_id, RouteRow.deleted_at.is_(None))
    ).one_or_none()
    if route is None:
        raise NotFoundError(error_codes.ROUTE_NOT_FOUND, id=route_id)

    now = deps.clock().now()
    today = now.date()

    current = session.scalars(
        select(FareRuleRow)
        .where(
            FareRuleRow.route_id == route_id,
            FareRuleRow.ride_kind == body.ride_kind,
            FareRuleRow.deleted_at.is_(None),
            FareRuleRow.valid_from <= today,
        )
        .order_by(FareRuleRow.valid_from.desc())
        .limit(1)
    ).one_or_none()
    if current is None:
        raise NotFoundError(error_codes.FARE_NOT_CONFIGURED, route_id=route_id)

    previous = current.amount_minor
    current.valid_to = today
    current.version += 1
    session.add(current)

    replacement = FareRuleRow(
        id=deps.new_id(),
        route_id=route_id,
        ride_kind=body.ride_kind,
        vehicle_type_code=current.vehicle_type_code,
        from_sequence=current.from_sequence,
        to_sequence=current.to_sequence,
        amount_minor=body.amount_minor,
        amount_currency=current.amount_currency,
        valid_from=today,
        notes=body.note,
        created_by=actor.user_id,
    )
    session.add(replacement)

    audit.write(
        "pricing.changed",
        actor_id=actor.user_id,
        actor_role=actor.role,
        entity_type="route",
        entity_id=route_id,
        before={"amount_minor": previous},
        after={"amount_minor": body.amount_minor, "ride_kind": body.ride_kind},
    )
    return ok(
        {
            "route_id": route_id,
            "previous_minor": previous,
            "amount_minor": body.amount_minor,
            "currency": current.amount_currency,
        }
    )


# -- drivers and vehicles ------------------------------------------------

class DriverAdminOut(Schema):
    id: str
    user_id: str
    full_name: str | None
    phone: str
    approval_status: str
    availability: str
    rating_average: float | None
    rating_count: int
    completed_trips: int
    plate_number: str | None
    vehicle_status: str | None
    #: Seconds since the handset last reported a position; null when it
    #: never has. A working driver with no recent fix is a car the office
    #: cannot send anywhere, which is why the dashboard counts them.
    location_age_seconds: int | None = None


@router.get("/drivers")
def drivers(
    actor: Annotated[deps.Actor, Depends(deps.require_staff)],
    session: deps.SessionDep,
    settings: Annotated[object, Depends(deps.app_settings)],
    approval_status: str | None = None,
    #: Only working drivers whose last fix is stale or missing -- the
    #: dashboard's "without a fix" card.
    stale_gps: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> dict:
    from infrastructure.db.models.supply import DriverLocationRow

    now = deps.clock().now()
    # Vehicles are fetched separately rather than joined. A driver may own more
    # than one, and an outer join then returns that driver once per vehicle: the
    # operator sees the same person twice in the approvals queue and cannot tell
    # the copies apart, and `limit` counts the duplicates, so a real driver falls
    # off the end of the list to make room for a repeat.
    stmt = (
        select(DriverRow, UserRow, DriverLocationRow.recorded_at)
        .join(UserRow, UserRow.id == DriverRow.user_id)
        .outerjoin(DriverLocationRow, DriverLocationRow.driver_id == DriverRow.id)
        .where(DriverRow.deleted_at.is_(None))
        .order_by(DriverRow.created_at.desc())
        .limit(limit)
    )
    if approval_status:
        stmt = stmt.where(DriverRow.approval_status == approval_status)
    if stale_gps:
        stale_after = timedelta(seconds=settings.get_int("dispatch.stale_gps_seconds", 300))
        stmt = stmt.where(*opscentre.stale_gps_clause(now, stale_after))

    rows = session.execute(stmt).all()
    vehicles = _one_vehicle_each(session, [d.id for d, _, _ in rows])

    return ok(
        [
            DriverAdminOut(
                id=d.id, user_id=d.user_id, full_name=u.full_name, phone=u.phone,
                approval_status=d.approval_status, availability=d.availability,
                rating_average=round(d.rating_sum / d.rating_count, 2)
                if d.rating_count else None,
                rating_count=d.rating_count, completed_trips=d.completed_trips,
                plate_number=(v := vehicles.get(d.id)) and v.plate_number,
                vehicle_status=v.status if v else None,
                location_age_seconds=(
                    max(0, int((now - seen).total_seconds())) if seen else None
                ),
            ).model_dump()
            for d, u, seen in rows
        ]
    )


def _one_vehicle_each(
    session: Session, driver_ids: list[str]
) -> dict[str, VehicleRow]:
    """The vehicle to show beside each driver in a list.

    The list has one plate column, so it shows one vehicle: the active one if
    there is one, otherwise the most recently registered. Deterministic on
    purpose -- a column that shows a different plate on each refresh is worse
    than one that shows an incomplete truth.
    """
    if not driver_ids:
        return {}
    rows = session.execute(
        select(VehicleRow)
        .where(
            VehicleRow.driver_id.in_(driver_ids),
            VehicleRow.deleted_at.is_(None),
        )
        .order_by(VehicleRow.created_at.desc())
    ).scalars().all()

    chosen: dict[str, VehicleRow] = {}
    for vehicle in rows:
        current = chosen.get(vehicle.driver_id)
        if current is None or (
            current.status != VehicleStatus.ACTIVE.value
            and vehicle.status == VehicleStatus.ACTIVE.value
        ):
            chosen[vehicle.driver_id] = vehicle
    return chosen


class DriverDecisionIn(Schema):
    reason: str | None = None


class ApproveDriverIn(Schema):
    # The name as it reads on the tazkira the operator is looking at.
    #
    # Every field is optional so that a caller who posts no body at all keeps
    # working, which several tests and the existing panel do.
    full_name: str | None = Field(default=None, max_length=160)


@router.post("/drivers/{driver_id}/approve")
def approve_driver(
    driver_id: str,
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    drivers_repo: Annotated[object, Depends(deps.drivers)],
    users: Annotated[object, Depends(deps.users)],
    settings: Annotated[object, Depends(deps.app_settings)],
    audit: Annotated[object, Depends(deps.audit)],
    body: ApproveDriverIn | None = None,
) -> dict:
    """Approval is what lets a driver receive work at all (section 28).

    The document check lives in the domain entity, so this cannot approve
    someone whose licence is missing however the request is shaped.

    This is also the best name VELRO ever gets, and the only place a wrong one
    can be put right. The operator is authenticated, is reading a tazkira, and
    has a decision to make -- so unlike the driver's own apply form, this may
    replace a name that is already there. Which matters: the apply form appears
    on whatever handset the household shares, and the name it collected may be
    a brother's, or a single letter typed to get past the field.
    """
    from domain.driver import Driver, DriverDocument
    from domain.enums import DocumentStatus

    row = drivers_repo.get(driver_id)
    now = deps.clock().now()

    driver = Driver(
        id=row.id,
        user_id=row.user_id,
        approval_status=row.approval_status,
        availability=row.availability,
        documents=[
            DriverDocument(
                id=d.id, driver_id=d.driver_id, document_type_code=d.document_type_code,
                file_key=d.file_key, status=DocumentStatus(d.status),
                expires_on=d.expires_on, uploaded_at=d.created_at,
            )
            for d in drivers_repo.documents_of(driver_id)
        ],
    )
    driver.approve(
        by=actor.user_id,
        at=now,
        required_documents=frozenset(settings.get_list("driver.required_documents", [])),
    )

    before = row.approval_status
    row.approval_status = driver.approval_status.value
    row.approved_at = now
    row.approved_by = actor.user_id
    row.suspended_reason = None
    drivers_repo.save(row)

    audit.write(
        "driver.approved",
        actor_id=actor.user_id,
        actor_role=actor.role,
        entity_type="driver",
        entity_id=driver_id,
        before={"approval_status": before},
        after={"approval_status": row.approval_status},
    )

    RecordName(users=users, audit=audit, clock=deps.clock()).execute(
        RecordNameCommand(
            user_id=row.user_id,
            actor_id=actor.user_id,
            raw_name=body.full_name if body else None,
            actor_role=actor.role,
            allow_overwrite=True,
        )
    )
    return ok({"driver_id": driver_id, "approval_status": row.approval_status})


@router.post("/drivers/{driver_id}/suspend")
def suspend_driver(
    driver_id: str,
    body: DriverDecisionIn,
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    drivers_repo: Annotated[object, Depends(deps.drivers)],
    trips: Annotated[object, Depends(deps.trips)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    from domain.driver import Driver

    row = drivers_repo.get(driver_id)

    # Refuse mid-trip: suspending a driver with passengers aboard would strand
    # them at the roadside, which is worse than whatever prompted it.
    in_flight = trips.active_for_driver(driver_id)
    if in_flight is not None:
        raise ConflictError(
            error_codes.DRIVER_ALREADY_ON_TRIP, driver_id=driver_id, trip_id=in_flight.id
        )

    driver = Driver(
        id=row.id, user_id=row.user_id,
        approval_status=row.approval_status, availability=row.availability,
    )
    before = row.approval_status
    driver.suspend(body.reason or "suspended by an administrator")

    row.approval_status = driver.approval_status.value
    row.availability = driver.availability.value
    row.suspended_reason = driver.suspended_reason
    drivers_repo.save(row)

    audit.write(
        "driver.suspended",
        actor_id=actor.user_id,
        actor_role=actor.role,
        entity_type="driver",
        entity_id=driver_id,
        before={"approval_status": before},
        after={"approval_status": row.approval_status, "reason": row.suspended_reason},
    )
    return ok({"driver_id": driver_id, "approval_status": row.approval_status})



# -- users ---------------------------------------------------------------


class UserAdminOut(Schema):
    id: str
    phone: str
    full_name: str | None
    status: str
    locale: str
    roles: list[str]
    rating_average: float | None
    rating_count: int
    created_at: datetime | None
    last_seen_at: datetime | None


class UserDecisionIn(Schema):
    reason: str | None = Field(default=None, max_length=300)


def _user_admin_out(row, roles: list[str]) -> dict:
    return UserAdminOut(
        id=row.id,
        phone=row.phone,
        full_name=row.full_name,
        status=row.status,
        locale=row.locale,
        roles=roles,
        rating_average=(row.rating_sum / row.rating_count) if row.rating_count else None,
        rating_count=row.rating_count,
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
    ).model_dump()


@router.get("/users")
def users_list(
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    session: deps.SessionDep,
    phone: Annotated[str | None, Query(max_length=20)] = None,
    status: Annotated[str | None, Query(pattern=r"^(ACTIVE|SUSPENDED|DEACTIVATED)$")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict:
    """Find an account, usually by the phone number in a driver's complaint.

    A contains-match on digits, because the complaint arrives as 0793..., the
    row holds +93793..., and the operator should not have to know which form
    the database speaks.
    """
    stmt = select(UserRow).where(UserRow.deleted_at.is_(None))
    if phone:
        digits = "".join(ch for ch in phone if ch.isdigit())
        stmt = stmt.where(UserRow.phone.contains(digits.lstrip("0") or digits))
    if status:
        stmt = stmt.where(UserRow.status == status)
    rows = session.scalars(
        stmt.order_by(UserRow.created_at.desc()).limit(limit)
    ).all()
    users_repo = deps.users(session)
    return ok(
        [_user_admin_out(row, users_repo.roles_of(row.id)) for row in rows],
        meta={"count": len(rows)},
    )


def _load_user(users_repo, user_id: str) -> DomainUser:
    row = users_repo.get(user_id)
    return DomainUser(
        id=row.id,
        phone=PhoneNumber(row.phone),
        full_name=row.full_name,
        locale=Locale(row.locale),
        status=UserStatus(row.status),
        roles=set(users_repo.roles_of(row.id)),
    ), row


@router.post("/users/{user_id}/suspend")
def suspend_user(
    user_id: str,
    body: UserDecisionIn,
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    session: deps.SessionDep,
    trips: Annotated[object, Depends(deps.trips)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    """The account-level off switch.

    This is what a confirmed troll gets: sign-in refuses him, and every
    request his surviving tokens make is refused on arrival, because the
    actor is re-read from this row each time. His next account costs him a
    new SIM.

    Suspending a user who also drives is allowed -- it is the stronger of the
    two levers, for conduct worse than paperwork -- but not while he has
    passengers aboard, for the same reason the driver-level suspend refuses:
    stranding them roadside is worse than whatever prompted this. A suspended
    passenger's existing bookings are left to play out through the no-show
    machinery; the switch stops new summonses, it does not tear up receipts.
    """
    users_repo = deps.users(session)
    user, row = _load_user(users_repo, user_id)

    if DRIVER_ROLE in user.roles:
        driver_row = deps.drivers(session).find_by_user(user_id)
        in_flight = trips.active_for_driver(driver_row.id) if driver_row else None
        if in_flight is not None:
            raise ConflictError(
                error_codes.DRIVER_ALREADY_ON_TRIP,
                driver_id=driver_row.id, trip_id=in_flight.id,
            )

    before = row.status
    user.suspend()
    row.status = user.status.value
    users_repo.save(row)

    audit.write(
        "user.suspended",
        actor_id=actor.user_id,
        actor_role=actor.role,
        entity_type="user",
        entity_id=user_id,
        before={"status": before},
        after={"status": row.status, "reason": body.reason},
    )
    return ok({"user_id": user_id, "status": row.status})


@router.post("/users/{user_id}/reinstate")
def reinstate_user(
    user_id: str,
    body: UserDecisionIn,
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    session: deps.SessionDep,
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    users_repo = deps.users(session)
    user, row = _load_user(users_repo, user_id)

    before = row.status
    user.reinstate()
    row.status = user.status.value
    users_repo.save(row)

    audit.write(
        "user.reinstated",
        actor_id=actor.user_id,
        actor_role=actor.role,
        entity_type="user",
        entity_id=user_id,
        before={"status": before},
        after={"status": row.status, "reason": body.reason},
    )
    return ok({"user_id": user_id, "status": row.status})


class VehicleAdminOut(Schema):
    id: str
    driver_id: str
    driver_name: str | None
    driver_phone: str | None
    vehicle_type_code: str
    plate_number: str
    seat_capacity: int
    brand: str | None
    model: str | None
    colour: str | None
    status: str


@router.get("/vehicles")
def vehicles(
    actor: Annotated[deps.Actor, Depends(deps.require_staff)],
    session: deps.SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> dict:
    stmt = (
        select(VehicleRow, UserRow.full_name, UserRow.phone)
        .join(DriverRow, DriverRow.id == VehicleRow.driver_id)
        .join(UserRow, UserRow.id == DriverRow.user_id)
        .where(VehicleRow.deleted_at.is_(None))
        .order_by(VehicleRow.plate_number)
        .limit(limit)
    )
    return ok(
        [
            VehicleAdminOut(
                id=v.id, driver_id=v.driver_id, driver_name=driver_name,
                driver_phone=driver_phone,
                vehicle_type_code=v.vehicle_type_code, plate_number=v.plate_number,
                seat_capacity=v.seat_capacity, brand=v.brand, model=v.model,
                colour=v.colour, status=v.status,
            ).model_dump()
            for v, driver_name, driver_phone in session.execute(stmt).all()
        ]
    )


# -- trips and bookings --------------------------------------------------

class TripAdminOut(Schema):
    id: str
    number: str
    status: str
    ride_kind: str
    scheduled_departure_at: datetime
    origin_station_name: str
    destination_name: str
    driver_name: str | None
    driver_phone: str | None
    plate_number: str | None
    seat_capacity: int
    seats_available: int
    booked_seats: int


@router.get("/trips")
def trips_list(
    actor: Annotated[deps.Actor, Depends(deps.require_staff)],
    session: deps.SessionDep,
    trips: Annotated[object, Depends(deps.trips)],
    status: str | None = None,
    active_only: bool = False,
    #: The dashboard's cards, as filters: the same clauses opscentre counts
    #: with, so the number on the card is the number of rows here.
    unassigned: bool = False,
    overdue: bool = False,
    departing_within_hours: Annotated[int | None, Query(ge=1, le=72)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """The live board (section 53), newest departures first."""
    now = deps.clock().now()
    stmt = (
        select(
            TripRow, StationRow.name, DestinationRow.name,
            UserRow.full_name, UserRow.phone, VehicleRow.plate_number,
        )
        .join(StationRow, StationRow.id == TripRow.origin_station_id)
        .join(DestinationRow, DestinationRow.id == TripRow.destination_id)
        .outerjoin(DriverRow, DriverRow.id == TripRow.driver_id)
        .outerjoin(UserRow, UserRow.id == DriverRow.user_id)
        .outerjoin(VehicleRow, VehicleRow.id == TripRow.vehicle_id)
        .where(TripRow.deleted_at.is_(None))
        .order_by(TripRow.scheduled_departure_at.desc())
    )
    if status:
        stmt = stmt.where(TripRow.status == status)
    if active_only:
        stmt = stmt.where(TripRow.status.in_(_ACTIVE_TRIP_STATUSES))
    if unassigned:
        stmt = stmt.where(*opscentre.needs_driver_clause(now))
    if overdue:
        stmt = stmt.where(*opscentre.overdue_clause(now))
    if departing_within_hours is not None:
        stmt = stmt.where(
            TripRow.scheduled_departure_at >= now,
            TripRow.scheduled_departure_at <= now + timedelta(hours=departing_within_hours),
        )
    if unassigned or departing_within_hours is not None:
        # Soonest first when the question is "what is about to leave".
        stmt = stmt.order_by(None).order_by(TripRow.scheduled_departure_at.asc())

    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = session.execute(stmt.limit(limit).offset(offset)).all()
    availability = trips.seats_available_map([r[0].id for r in rows])

    return ok(
        [
            TripAdminOut(
                id=t.id, number=t.number, status=t.status, ride_kind=t.ride_kind,
                scheduled_departure_at=t.scheduled_departure_at,
                origin_station_name=origin, destination_name=destination,
                driver_name=driver_name, driver_phone=driver_phone, plate_number=plate,
                seat_capacity=t.seat_capacity,
                seats_available=availability.get(t.id, 0),
                booked_seats=t.seat_capacity - availability.get(t.id, 0),
            ).model_dump()
            for t, origin, destination, driver_name, driver_phone, plate in rows
        ],
        meta={"total": int(total or 0), "limit": limit, "offset": offset},
    )


class BookingAdminOut(Schema):
    id: str
    number: str
    trip_number: str
    passenger_name: str | None
    passenger_phone: str
    status: str
    seat_count: int
    fare_total_minor: int
    fare_currency: str
    payment_method: str
    payment_status: str | None
    created_at: datetime


@router.get("/bookings")
def bookings_list(
    actor: Annotated[deps.Actor, Depends(deps.require_staff)],
    session: deps.SessionDep,
    status: str | None = None,
    trip_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    stmt = (
        select(BookingRow, TripRow.number, UserRow.full_name, UserRow.phone, PaymentRow.status)
        .join(TripRow, TripRow.id == BookingRow.trip_id)
        .join(UserRow, UserRow.id == BookingRow.passenger_id)
        .outerjoin(PaymentRow, PaymentRow.booking_id == BookingRow.id)
        .where(BookingRow.deleted_at.is_(None))
        .order_by(BookingRow.created_at.desc())
    )
    if status:
        stmt = stmt.where(BookingRow.status == status)
    if trip_id:
        stmt = stmt.where(BookingRow.trip_id == trip_id)

    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = session.execute(stmt.limit(limit).offset(offset)).all()
    return ok(
        [
            BookingAdminOut(
                id=b.id, number=b.number, trip_number=trip_number,
                passenger_name=name, passenger_phone=phone, status=b.status,
                seat_count=b.seat_count, fare_total_minor=b.fare_total_minor,
                fare_currency=b.fare_total_currency, payment_method=b.payment_method,
                payment_status=payment_status, created_at=b.created_at,
            ).model_dump()
            # The verification code is deliberately absent: it boards a
            # passenger, and staff have no reason to see it.
            for b, trip_number, name, phone, payment_status in rows
        ],
        meta={"total": int(total or 0), "limit": limit, "offset": offset},
    )


# -- finance -------------------------------------------------------------

class FinanceOut(Schema):
    period_start: date
    period_end: date
    gross_minor: int
    platform_minor: int
    driver_minor: int
    currency: str
    completed_bookings: int
    cash_minor: int
    online_minor: int
    pending_settlement_minor: int
    paid_settlement_minor: int


@router.get("/finance")
def finance(
    actor: Annotated[deps.Actor, Depends(deps.require_finance)],
    session: deps.SessionDep,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> dict:
    """Section 55. Every figure comes from the stored split, never recomputed
    from a rate that may have changed since."""
    now = deps.clock().now()
    start = (now - timedelta(days=days)).astimezone(KABUL).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    window = (
        CommissionRow.created_at >= start,
        CommissionRow.deleted_at.is_(None),
    )

    def total(column, *where) -> int:
        return int(session.scalar(select(func.coalesce(func.sum(column), 0)).where(*where)) or 0)

    cash = total(
        PaymentRow.amount_minor,
        PaymentRow.created_at >= start,
        PaymentRow.method == "CASH",
        PaymentRow.status == "COLLECTED",
        PaymentRow.deleted_at.is_(None),
    )
    online = total(
        PaymentRow.amount_minor,
        PaymentRow.created_at >= start,
        PaymentRow.method != "CASH",
        PaymentRow.status == "COLLECTED",
        PaymentRow.deleted_at.is_(None),
    )

    from infrastructure.db.models.money import SettlementRow, WalletRow

    return ok(
        FinanceOut(
            period_start=start.date(),
            period_end=now.astimezone(KABUL).date(),
            gross_minor=total(CommissionRow.gross_minor, *window),
            platform_minor=total(CommissionRow.platform_minor, *window),
            driver_minor=total(CommissionRow.driver_minor, *window),
            currency="AFN",
            completed_bookings=int(
                session.scalar(
                    select(func.count()).select_from(CommissionRow).where(*window)
                ) or 0
            ),
            cash_minor=cash,
            online_minor=online,
            # What drivers are owed but have not been paid.
            pending_settlement_minor=total(
                WalletRow.available_minor, WalletRow.deleted_at.is_(None)
            ),
            paid_settlement_minor=total(
                SettlementRow.amount_minor,
                SettlementRow.status == "PAID",
                SettlementRow.deleted_at.is_(None),
            ),
        ).model_dump()
    )


# -- settings ------------------------------------------------------------

class SettingOut(Schema):
    key: str
    value: object
    value_type: str
    description_key: str | None


class UpdateSettingIn(Schema):
    value: object


@router.get("/settings")
def settings_list(
    actor: Annotated[deps.Actor, Depends(deps.require_admin)],
    session: deps.SessionDep,
) -> dict:
    """Everything an operator may change without a deploy (section 104)."""
    from infrastructure.services.settings import _unwrap

    rows = session.scalars(
        select(SettingRow).where(SettingRow.deleted_at.is_(None)).order_by(SettingRow.key)
    ).all()
    return ok(
        [
            SettingOut(
                key=r.key, value=_unwrap(r.value), value_type=r.value_type,
                description_key=r.description_key,
            ).model_dump()
            for r in rows
            if not r.is_secret
        ]
    )


@router.patch("/settings/{key}")
def update_setting(
    key: str,
    body: UpdateSettingIn,
    actor: Annotated[deps.Actor, Depends(deps.require_admin)],
    session: deps.SessionDep,
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    from infrastructure.services.settings import _unwrap, wrap

    row = session.scalars(
        select(SettingRow).where(SettingRow.key == key, SettingRow.deleted_at.is_(None))
    ).one_or_none()
    if row is None:
        raise NotFoundError(error_codes.SETTING_NOT_FOUND, key=key)

    before = _unwrap(row.value)
    if type(body.value).__name__ != row.value_type:
        raise ConflictError(
            error_codes.SETTING_TYPE_INVALID,
            key=key, expected=row.value_type, got=type(body.value).__name__,
        )

    row.value = wrap(body.value)
    row.updated_by = actor.user_id
    row.version += 1
    session.add(row)

    audit.write(
        "settings.changed",
        actor_id=actor.user_id,
        actor_role=actor.role,
        entity_type="app_setting",
        entity_id=row.id,
        before={"key": key, "value": before},
        after={"key": key, "value": body.value},
    )
    return ok({"key": key, "value": body.value})


# -- crashes --------------------------------------------------------------


@router.get("/crashes")
def crashes(
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    session: deps.SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict:
    """The handsets' dying words, newest first.

    Read when a tester says "it closed by itself": the stack that reached
    this table on the next launch is the whole story, and without this
    surface it would be sitting in Postgres where nobody looks.
    """
    from infrastructure.db.models.ops import CrashReportRow

    rows = session.scalars(
        select(CrashReportRow)
        .order_by(CrashReportRow.received_at.desc())
        .limit(limit)
    ).all()
    return ok([
        {
            "id": r.id, "app": r.app,
            "version_code": r.version_code, "version_name": r.version_name,
            "device": r.device, "sdk": r.sdk,
            "occurred_at": r.occurred_at, "received_at": r.received_at,
            "stack": r.stack,
        }
        for r in rows
    ], meta={"count": len(rows)})


# -- audit ---------------------------------------------------------------

class AuditOut(Schema):
    id: str
    occurred_at: datetime
    actor_id: str | None
    actor_name: str | None
    actor_role: str
    action: str
    entity_type: str
    entity_id: str
    before: dict | None
    after: dict | None
    origin: str


@router.get("/audit")
def audit_log(
    actor: Annotated[deps.Actor, Depends(deps.require_admin)],
    session: deps.SessionDep,
    action: str | None = None,
    entity_type: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """Section 59. Append-only and never rotated; this is the read side."""
    stmt = (
        select(AuditLogRow, UserRow.full_name)
        .outerjoin(UserRow, UserRow.id == AuditLogRow.actor_id)
        .order_by(AuditLogRow.occurred_at.desc())
    )
    if action:
        stmt = stmt.where(AuditLogRow.action == action)
    if entity_type:
        stmt = stmt.where(AuditLogRow.entity_type == entity_type)

    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = session.execute(stmt.limit(limit).offset(offset)).all()
    return ok(
        [
            AuditOut(
                id=a.id, occurred_at=a.occurred_at, actor_id=a.actor_id,
                actor_name=name, actor_role=a.actor_role, action=a.action,
                entity_type=a.entity_type, entity_id=a.entity_id,
                before=a.before, after=a.after, origin=a.origin,
            ).model_dump()
            for a, name in rows
        ],
        meta={"total": int(total or 0), "limit": limit, "offset": offset},
    )
