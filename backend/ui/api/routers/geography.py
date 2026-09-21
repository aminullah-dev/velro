"""Geography: browse, search, nearby, and the cached snapshot.

Section 15 gives three ways to choose an origin because none works alone here:
search needs the passenger to know the spelling, browsing needs them to know
their district, and nearby needs a GPS fix that a valley often will not give.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import Field
from sqlalchemy import func, select

from application.use_cases.report_place import ReportPlace, ReportPlaceCommand
from domain.enums import PlaceStatus
from domain.places import assert_allowed, place_key
from infrastructure.db.models.geography import DistrictRow, PlaceRow, StationRow, VillageRow
from shared import error_codes
from shared.errors import NotFoundError, ValidationError
from ui.api import deps
from ui.api.errors import ok
from ui.api.geofence import DEFAULT_RADIUS_M, SETTING_RADIUS_M, assert_inside
from ui.api.schemas.common import Schema
from ui.api.schemas.geography import (
    DestinationGroupOut,
    DestinationOut,
    DistrictOut,
    GeoSnapshotOut,
    NearbyStationOut,
    PlaceIn,
    PlaceOut,
    ResolveOut,
    SearchResultOut,
    StationOut,
    VillageOut,
)

router = APIRouter(prefix="/geo", tags=["geography"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])

#: Approved names offered to a passenger are the ones within walking distance.
PLACES_NEAR_M = 3_000

#: A fix vaguer than this cannot name a spot: at Android's coarse accuracy the
#: "place" could be any of three villages. The app asks for a precise fix
#: first and only offers naming once it has one.
MAX_NAMING_ACCURACY_M = 300


@router.get("/districts")
def list_districts(
    geo: Annotated[object, Depends(deps.geography)],
    province_id: str | None = None,
) -> dict:
    rows = geo.list_districts(province_id=province_id)
    return ok([DistrictOut.model_validate(r).model_dump() for r in rows])


@router.get("/districts/{district_id}/villages")
def list_villages(
    district_id: str,
    geo: Annotated[object, Depends(deps.geography)],
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    rows = geo.list_villages(district_id, limit=limit, offset=offset)
    aliases = geo.aliases_for([r.id for r in rows])
    return ok(
        [
            VillageOut(
                id=r.id, code=r.code, name=r.name, district_id=r.district_id,
                alternative_names=aliases.get(r.id, []),
                latitude=r.latitude, longitude=r.longitude,
            ).model_dump()
            for r in rows
        ]
    )


@router.get("/villages/{village_id}/stations")
def list_stations(
    village_id: str,
    geo: Annotated[object, Depends(deps.geography)],
) -> dict:
    rows = geo.list_stations(village_id)
    return ok([StationOut.model_validate(r).model_dump() for r in rows])


@router.get("/search")
def search_places(
    geo: Annotated[object, Depends(deps.geography)],
    q: Annotated[str, Query(min_length=1, max_length=80)] = "",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> dict:
    """Searches names, normalised keys and aliases.

    Matching on the normalised key is what lets someone typing with an Arabic
    yeh find a village stored with a Persian one.
    """
    villages = geo.search_villages(q, limit=limit)
    # Which alias brought each village back, so a result under a name the
    # passenger did not type can explain itself.
    matched = geo.aliases_matching(q, [v.id for v in villages])
    stations = geo.search_stations(q, limit=limit)
    results = [
        SearchResultOut(
            kind="village", id=v.id, code=v.code, name=v.name,
            district_id=v.district_id, matched_alias=matched.get(v.id),
        ).model_dump()
        for v in villages
    ] + [
        SearchResultOut(
            kind="station", id=s.id, code=s.code, name=s.name,
            district_id=s.district_id, village_id=s.village_id,
        ).model_dump()
        for s in stations
    ]
    return ok(results, meta={"query": q, "count": len(results)})


@router.get("/stations/nearby")
def nearby_stations(
    geo: Annotated[object, Depends(deps.geography)],
    latitude: Annotated[Decimal, Query()],
    longitude: Annotated[Decimal, Query()],
    radius_m: Annotated[int, Query(ge=100, le=100_000)] = 15_000,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> dict:
    pairs = geo.nearby_stations(latitude, longitude, radius_m=radius_m, limit=limit)
    return ok(
        [
            NearbyStationOut(
                **StationOut.model_validate(row).model_dump(), distance_m=distance
            ).model_dump()
            for row, distance in pairs
        ]
    )


@router.get("/resolve")
def resolve(
    geo: Annotated[object, Depends(deps.geography)],
    app_settings: Annotated[object, Depends(deps.app_settings)],
    latitude: Annotated[Decimal, Query(ge=-90, le=90)],
    longitude: Annotated[Decimal, Query(ge=-180, le=180)],
) -> dict:
    """Where am I, for the passenger who tapped "my current location".

    Nothing is written. The coordinates arrive in the query string, which the
    request log does not record (it logs the path only), and leave with the
    response -- exactly as /stations/nearby has always worked, and as the
    privacy page tells passengers.
    """
    radius = app_settings.get_int(SETTING_RADIUS_M, DEFAULT_RADIUS_M)
    if radius <= 0:
        radius = DEFAULT_RADIUS_M
    stations = geo.nearby_stations(latitude, longitude, radius_m=radius, limit=3)
    located = geo.nearest_district(latitude, longitude, radius_m=radius)
    places = geo.places_near(latitude, longitude, radius_m=PLACES_NEAR_M, limit=10)
    return ok(
        ResolveOut(
            inside=bool(stations),
            district=DistrictOut.model_validate(located[0]) if located else None,
            district_source=located[1] if located else None,
            stations=[
                NearbyStationOut(
                    **StationOut.model_validate(row).model_dump(), distance_m=distance
                )
                for row, distance in stations
            ],
            places=[_place_out(row, distance) for row, distance in places],
        ).model_dump()
    )


@router.get("/places/nearby")
def nearby_places(
    geo: Annotated[object, Depends(deps.geography)],
    latitude: Annotated[Decimal, Query(ge=-90, le=90)],
    longitude: Annotated[Decimal, Query(ge=-180, le=180)],
    radius_m: Annotated[int, Query(ge=100, le=10_000)] = PLACES_NEAR_M,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> dict:
    """Approved names near a fix. Never a PENDING one: those are nobody's but
    the person who typed them until staff have read them."""
    pairs = geo.places_near(latitude, longitude, radius_m=radius_m, limit=limit)
    return ok([_place_out(row, distance).model_dump() for row, distance in pairs])


@router.post("/places", status_code=201)
def name_place(
    body: PlaceIn,
    actor: deps.ActorDep,
    geo: Annotated[object, Depends(deps.geography)],
    app_settings: Annotated[object, Depends(deps.app_settings)],
) -> dict:
    """The passenger says what the place they are standing in is called.

    Signed in, so a stranger with a script cannot fill the valley with names;
    fenced like the ride request, so the names are from people who are there.
    But the row it writes is anonymous -- no user column, no created_by, no
    audit entry naming anyone (ADR 0015). The actor is checked, not recorded.
    """
    assert_inside(
        geo=geo,
        app_settings=app_settings,
        exempt_phones=deps.settings().geofence_exempt_phones,
        phone=deps.users(geo.session).get(actor.user_id).phone,
        latitude=body.latitude,
        longitude=body.longitude,
        is_mock=body.location_is_mock,
    )
    if body.accuracy_m is not None and body.accuracy_m > MAX_NAMING_ACCURACY_M:
        raise ValidationError(
            error_codes.PLACE_FIX_TOO_COARSE, accuracy_m=int(body.accuracy_m)
        )
    row = ReportPlace(geography=geo, clock=deps.clock(), new_id=deps.new_id).execute(
        ReportPlaceCommand(
            name=body.name,
            latitude=body.latitude,
            longitude=body.longitude,
            district_id=body.district_id,
        )
    )
    geo.session.flush()
    return ok(_place_out(row, None).model_dump())


def _place_out(row, distance: int | None) -> PlaceOut:
    return PlaceOut(
        id=row.id,
        name=row.name,
        district_id=row.district_id,
        village_id=row.village_id,
        nearest_station_id=row.nearest_station_id,
        latitude=row.latitude,
        longitude=row.longitude,
        status=row.status,
        distance_m=distance,
    )


@router.get("/stations/{station_id}/destinations")
def destinations_from(
    station_id: str,
    geo: Annotated[object, Depends(deps.geography)],
) -> dict:
    """Only what this origin can actually reach.

    Section 16: a passenger is never shown a menu of places no vehicle goes.
    Children are nested under their parent, so Kabul appears once with Khair
    Khana Mina and Jada beneath it.
    """
    reachable = geo.destinations_reachable_from(station_id)
    by_id = {d.id: d for d in reachable}

    # A child is reachable but its parent may not be a destination in its own
    # right; fetch parents so the grouping is complete.
    parents: dict[str, object] = {}
    for row in reachable:
        if row.parent_id and row.parent_id not in by_id:
            parents[row.parent_id] = geo.get_destination(row.parent_id)

    groups: list[dict] = []
    standalone = [d for d in reachable if d.parent_id is None]
    for row in standalone:
        children = [c for c in reachable if c.parent_id == row.id]
        groups.append(
            DestinationGroupOut(
                id=row.id, code=row.code, name=row.name, kind=row.kind,
                children=[DestinationOut.model_validate(c) for c in children],
            ).model_dump()
        )
    for parent_id, parent in parents.items():
        children = [c for c in reachable if c.parent_id == parent_id]
        groups.append(
            DestinationGroupOut(
                id=parent.id, code=parent.code, name=parent.name, kind=parent.kind,
                children=[DestinationOut.model_validate(c) for c in children],
            ).model_dump()
        )
    return ok(groups)


@router.get("/snapshot", response_model=None)
def snapshot(
    response: Response,
    geo: Annotated[object, Depends(deps.geography)],
    if_none_match: Annotated[str | None, Query(alias="version")] = None,
) -> dict | Response:
    """The whole hierarchy, cached by version.

    Geography changes a few times a year. Returning 304 when the client already
    has the current version is the single biggest saving available on a 2G
    connection, and it is why the booking flow works with almost no data.
    """
    version = geo.snapshot_version()
    response.headers["ETag"] = version
    response.headers["Cache-Control"] = "private, max-age=3600"
    if if_none_match == version:
        return Response(status_code=304, headers={"ETag": version})

    payload = GeoSnapshotOut(
        version=version,
        districts=[DistrictOut.model_validate(r) for r in geo.list_districts()],
        villages=[
            VillageOut.model_validate(v)
            for d in geo.list_districts()
            for v in geo.list_villages(d.id, limit=500)
        ],
        stations=[
            StationOut.model_validate(s)
            for d in geo.list_districts()
            for v in geo.list_villages(d.id, limit=500)
            for s in geo.list_stations(v.id)
        ],
        destinations=[DestinationOut.model_validate(d) for d in geo.list_destinations()],
    )
    return ok(payload.model_dump())


# -- staff: reading the names ------------------------------------------------

class PlaceAdminOut(Schema):
    id: str
    name: str
    status: str
    district_id: str
    district_name: str
    #: The known village the name matched, if it matched one.
    village_id: str | None = None
    village_name: str | None = None
    nearest_station_name: str | None = None
    latitude: float
    longitude: float
    #: How many times it was typed here. Many passengers giving one name is
    #: the strongest evidence a place is called that.
    report_count: int
    last_reported_at: str
    created_at: str


class PlaceDecisionIn(Schema):
    #: Approve under a corrected spelling -- the name people use, written the
    #: way the village list writes it. Omitted keeps what was typed.
    name: str | None = Field(default=None, max_length=120)


@admin_router.get("/places")
def places_for_review(
    actor: Annotated[deps.Actor, Depends(deps.require_staff)],
    session: deps.SessionDep,
    status: Annotated[str | None, Query(pattern=r"^(APPROVED|PENDING|REJECTED)$")] = "PENDING",
    district_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """Names passengers gave, most-reported first.

    The queue staff clear: a PENDING name is shown to no other passenger until
    somebody here has read it and said it is a place.
    """
    stmt = (
        select(PlaceRow, DistrictRow.name, VillageRow.name, StationRow.name)
        .join(DistrictRow, DistrictRow.id == PlaceRow.district_id)
        .outerjoin(VillageRow, VillageRow.id == PlaceRow.village_id)
        .outerjoin(StationRow, StationRow.id == PlaceRow.nearest_station_id)
        .where(PlaceRow.deleted_at.is_(None))
        .order_by(PlaceRow.report_count.desc(), PlaceRow.last_reported_at.desc())
    )
    if status:
        stmt = stmt.where(PlaceRow.status == status)
    if district_id:
        stmt = stmt.where(PlaceRow.district_id == district_id)
    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = session.execute(stmt.limit(limit).offset(offset)).all()
    return ok(
        [
            PlaceAdminOut(
                id=p.id, name=p.name, status=p.status,
                district_id=p.district_id, district_name=district_name,
                village_id=p.village_id, village_name=village_name,
                nearest_station_name=station_name,
                latitude=float(p.latitude), longitude=float(p.longitude),
                report_count=p.report_count,
                last_reported_at=p.last_reported_at.isoformat(),
                created_at=p.created_at.isoformat(),
            ).model_dump()
            for p, district_name, village_name, station_name in rows
        ],
        meta={"total": int(total or 0), "limit": limit, "offset": offset},
    )


@admin_router.post("/places/{place_id}/approve")
def approve_place(
    place_id: str,
    body: PlaceDecisionIn,
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    geo: Annotated[object, Depends(deps.geography)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    """This is a place, and every passenger near it may now be offered it.

    A corrected spelling goes through the same filter a passenger's does:
    staff are trusted to judge, not to skip the rule that keeps a household
    off the map.
    """
    return ok(_decide(place_id, PlaceStatus.APPROVED, body.name, actor, geo, audit))


@admin_router.post("/places/{place_id}/reject")
def reject_place(
    place_id: str,
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    geo: Annotated[object, Depends(deps.geography)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    """Not a place. Kept, not deleted: the next passenger typing the same name
    here is told so, instead of putting it back in the queue."""
    return ok(_decide(place_id, PlaceStatus.REJECTED, None, actor, geo, audit))


def _decide(place_id, status: PlaceStatus, rename, actor, geo, audit) -> dict:
    row = geo.find_place(place_id)
    if row is None:
        raise NotFoundError(error_codes.PLACE_NOT_FOUND, place_id=place_id)
    if row.status == status.value and rename is None:
        # A second tap on the same button, or two staff clearing the queue at
        # once. The answer is already the one asked for; nothing to record.
        return _place_out(row, None).model_dump()
    before = {"status": row.status, "name": row.name}
    if rename is not None:
        row.name = assert_allowed(rename)
        row.name_key = place_key(row.name)
    row.status = status.value
    row.updated_by = actor.user_id
    row.version += 1
    # The staff member is named; the passenger never was. Deciding about a
    # place is work somebody answers for; standing in one is not.
    audit.write(
        f"place.{status.value.lower()}",
        actor_id=actor.user_id,
        actor_role=actor.role,
        entity_type="place",
        entity_id=row.id,
        before=before,
        after={"status": row.status, "name": row.name},
    )
    geo.session.flush()
    return _place_out(row, None).model_dump()
