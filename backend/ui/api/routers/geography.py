"""Geography: browse, search, nearby, and the cached snapshot.

Section 15 gives three ways to choose an origin because none works alone here:
search needs the passenger to know the spelling, browsing needs them to know
their district, and nearby needs a GPS fix that a valley often will not give.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from ui.api import deps
from ui.api.errors import ok
from ui.api.schemas.geography import (
    DestinationGroupOut,
    DestinationOut,
    DistrictOut,
    GeoSnapshotOut,
    NearbyStationOut,
    SearchResultOut,
    StationOut,
    VillageOut,
)

router = APIRouter(prefix="/geo", tags=["geography"])


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
    return ok([VillageOut.model_validate(r).model_dump() for r in rows])


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
    stations = geo.search_stations(q, limit=limit)
    results = [
        SearchResultOut(
            kind="village", id=v.id, code=v.code, name=v.name, district_id=v.district_id
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
