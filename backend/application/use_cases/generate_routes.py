"""Materialising routes from templates.

Section 12 forbids hand-wiring a route per village. A template says "every
station in Siahgird can reach Charikar"; this generates the concrete routes and
their stops, and re-running it updates rather than duplicates.

Adding a village to a district therefore gives it a full set of routes without
anyone touching the routing tables.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.enums import ActorRole, OriginScope, RouteStatus
from shared import error_codes
from shared.clock import Clock
from shared.errors import NotFoundError
from shared.ids import IdGenerator


@dataclass(frozen=True, slots=True)
class GenerateRoutesCommand:
    template_id: str | None = None      # None regenerates every active template
    actor_id: str = "system"
    actor_role: ActorRole = ActorRole.SYSTEM
    activate: bool = True


@dataclass(frozen=True, slots=True)
class GenerateRoutesResult:
    templates_processed: int
    routes_created: int
    routes_updated: int
    stations_covered: int


class GenerateRoutes:
    def __init__(
        self, *, templates, routes, route_stops, geography, audit,
        clock: Clock, new_id: IdGenerator,
    ) -> None:
        self._templates = templates
        self._routes = routes
        self._stops = route_stops
        self._geography = geography
        self._audit = audit
        self._clock = clock
        self._new_id = new_id

    def execute(self, cmd: GenerateRoutesCommand) -> GenerateRoutesResult:
        templates = (
            [self._templates.get(cmd.template_id)]
            if cmd.template_id
            else self._templates.list_active()
        )

        created = updated = covered = 0
        for template in templates:
            stations = self._stations_in_scope(template)
            if not stations:
                # An empty scope is a configuration mistake worth surfacing, not
                # a silent no-op that leaves an operator wondering.
                raise NotFoundError(
                    error_codes.ROUTE_TEMPLATE_SCOPE_EMPTY,
                    template_id=template.id,
                    scope=template.origin_scope,
                    ref_id=template.origin_ref_id,
                )
            covered += len(stations)
            for station in stations:
                was_new = self._materialise(template, station, activate=cmd.activate)
                created += int(was_new)
                updated += int(not was_new)

        self._audit.write(
            "route.generated",
            actor_id=cmd.actor_id,
            actor_role=cmd.actor_role,
            entity_type="route_template",
            entity_id=cmd.template_id or "all",
            after={
                "templates": len(templates),
                "created": created,
                "updated": updated,
                "stations": covered,
            },
            origin="job",
        )
        return GenerateRoutesResult(len(templates), created, updated, covered)

    def _stations_in_scope(self, template) -> list:
        scope = OriginScope(template.origin_scope)
        if scope is OriginScope.STATION:
            return [self._geography.get_station(template.origin_ref_id)]
        if scope is OriginScope.VILLAGE:
            return self._geography.list_stations(template.origin_ref_id)
        villages = self._geography.list_villages(template.origin_ref_id, limit=500)
        return [s for v in villages for s in self._geography.list_stations(v.id)]

    def _materialise(self, template, station, *, activate: bool) -> bool:
        """Create or refresh one concrete route. Returns True when newly created."""
        existing = self._routes.find_by(
            origin_station_id=station.id,
            destination_id=template.destination_id,
            template_id=template.id,
        )
        status = (
            RouteStatus.ACTIVE.value
            if activate and template.status == RouteStatus.ACTIVE.value
            else RouteStatus.DRAFT.value
        )

        if existing is not None:
            existing.route_type = template.route_type
            existing.distance_m = template.distance_m
            existing.duration_minutes = template.duration_minutes
            existing.status = status
            self._routes.save(existing)
            self._rebuild_stops(existing, template, station)
            return False

        route = self._routes.create(
            id=self._new_id(),
            code=f"{template.code}-{station.code}",
            route_type=template.route_type,
            origin_station_id=station.id,
            destination_id=template.destination_id,
            template_id=template.id,
            distance_m=template.distance_m,
            duration_minutes=template.duration_minutes,
            status=status,
        )
        self._routes.session.flush()
        self._rebuild_stops(route, template, station)
        return True

    def _rebuild_stops(self, route, template, station) -> None:
        """Origin station, then any intermediate destinations, then the target.

        Rebuilt rather than patched: a template whose intermediate stops changed
        must not leave an orphaned stop behind at the old sequence.
        """
        for stop in self._stops.list(route_id=route.id, limit=200):
            self._stops.soft_delete(stop, at=self._clock.now())
        self._routes.session.flush()

        sequence = 0
        self._stops.create(
            id=self._new_id(), route_id=route.id, sequence=sequence,
            station_id=station.id, is_pickup=True, is_dropoff=False,
        )
        for destination_id in template.intermediate_destination_ids or []:
            sequence += 1
            self._stops.create(
                id=self._new_id(), route_id=route.id, sequence=sequence,
                destination_id=destination_id, is_pickup=True, is_dropoff=True,
            )
        sequence += 1
        self._stops.create(
            id=self._new_id(), route_id=route.id, sequence=sequence,
            destination_id=template.destination_id, is_pickup=False, is_dropoff=True,
        )
