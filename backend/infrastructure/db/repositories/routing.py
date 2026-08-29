"""Route and fare repositories."""

from __future__ import annotations

from datetime import date

from sqlalchemy import or_, select

from domain.enums import RouteStatus
from infrastructure.db.models.routing import (
    FareRuleRow,
    RouteRow,
    RouteScheduleRow,
    RouteStopRow,
    RouteTemplateRow,
    VehicleTypeRow,
)
from infrastructure.db.repositories.base import SqlRepository
from shared import error_codes


class RouteRepository(SqlRepository[RouteRow]):
    model = RouteRow
    not_found_code = error_codes.ROUTE_NOT_FOUND

    def find_for(self, origin_station_id: str, destination_id: str):
        """The active route between two places, if one has been generated.

        A negotiated ride does not need one -- two people agreed to make the
        journey whether or not VELRO has modelled it -- so this returns None
        rather than raising, and the trip simply carries no route.
        """
        return self.session.scalars(
            self._base()
            .where(
                RouteRow.origin_station_id == origin_station_id,
                RouteRow.destination_id == destination_id,
                RouteRow.status == RouteStatus.ACTIVE.value,
            )
            .order_by(RouteRow.code)
        ).first()

    def stops_of(self, route_id: str) -> list[RouteStopRow]:
        stmt = (
            select(RouteStopRow)
            .where(RouteStopRow.route_id == route_id, RouteStopRow.deleted_at.is_(None))
            .order_by(RouteStopRow.sequence)
        )
        return list(self.session.scalars(stmt).all())

    def find_serving(self, origin_station_id: str, destination_id: str) -> list[RouteRow]:
        """Routes that carry a passenger from this station to this destination.

        Two cases, and both matter: the route whose endpoints are exactly these,
        and the longer route that passes through both in order. The second is
        how a passenger boards at an intermediate village on a Kabul run.
        """
        direct = select(RouteRow.id).where(
            RouteRow.origin_station_id == origin_station_id,
            RouteRow.destination_id == destination_id,
        )
        pickup = select(RouteStopRow.route_id).where(
            RouteStopRow.station_id == origin_station_id,
            RouteStopRow.is_pickup.is_(True),
            RouteStopRow.deleted_at.is_(None),
        )
        dropoff = select(RouteStopRow.route_id).where(
            RouteStopRow.destination_id == destination_id,
            RouteStopRow.is_dropoff.is_(True),
            RouteStopRow.deleted_at.is_(None),
        )
        stmt = self._base().where(
            RouteRow.status == RouteStatus.ACTIVE.value,
            or_(RouteRow.id.in_(direct), RouteRow.id.in_(pickup.intersect(dropoff))),
        )
        candidates = list(self.session.scalars(stmt).all())

        # Confirm travelling order in Python: expressing "sequence of pickup is
        # less than sequence of dropoff" in SQL costs a second join for no gain
        # at this cardinality.
        serving: list[RouteRow] = []
        for route in candidates:
            stops = {
                (s.station_id or s.destination_id): (s.sequence, s.is_pickup, s.is_dropoff)
                for s in self.stops_of(route.id)
            }
            origin = stops.get(origin_station_id)
            target = stops.get(destination_id)
            if origin and target and origin[0] < target[0] and origin[1] and target[2]:
                serving.append(route)
        return serving

    def find_by_endpoints(self, origin_station_id: str, destination_id: str) -> RouteRow | None:
        return self.find_by(
            origin_station_id=origin_station_id, destination_id=destination_id
        )

    def schedules_of(self, route_id: str, *, on: date | None = None) -> list[RouteScheduleRow]:
        stmt = self.session.query if False else select(RouteScheduleRow).where(
            RouteScheduleRow.route_id == route_id,
            RouteScheduleRow.deleted_at.is_(None),
            RouteScheduleRow.is_active.is_(True),
        )
        if on is not None:
            stmt = stmt.where(
                RouteScheduleRow.active_from <= on,
                or_(
                    RouteScheduleRow.active_to.is_(None),
                    RouteScheduleRow.active_to >= on,
                ),
            )
        return list(self.session.scalars(stmt.order_by(RouteScheduleRow.departure_time)).all())


class RouteTemplateRepository(SqlRepository[RouteTemplateRow]):
    model = RouteTemplateRow
    not_found_code = error_codes.ROUTE_NOT_FOUND

    def list_active(self) -> list[RouteTemplateRow]:
        return list(
            self.session.scalars(
                self._base().where(RouteTemplateRow.status == RouteStatus.ACTIVE.value)
            ).all()
        )


class RouteStopRepository(SqlRepository[RouteStopRow]):
    model = RouteStopRow
    not_found_code = error_codes.ROUTE_NOT_FOUND


class RouteScheduleRepository(SqlRepository[RouteScheduleRow]):
    model = RouteScheduleRow
    not_found_code = error_codes.ROUTE_NOT_FOUND


class VehicleTypeRepository(SqlRepository[VehicleTypeRow]):
    """Sedan, SUV, Van, Hiace, Bus, Other -- rows, so an operator can add one
    without a deploy (section 105)."""

    model = VehicleTypeRow
    not_found_code = error_codes.VEHICLE_TYPE_UNKNOWN

    def find_by_code(self, code: str) -> VehicleTypeRow | None:
        return self.find_by(code=code.strip().upper())

    def active(self) -> list[VehicleTypeRow]:
        stmt = (
            self._base()
            .where(VehicleTypeRow.is_active.is_(True))
            .order_by(VehicleTypeRow.sort_order)
        )
        return list(self.session.scalars(stmt).all())


class FareRepository(SqlRepository[FareRuleRow]):
    model = FareRuleRow
    not_found_code = error_codes.FARE_NOT_CONFIGURED

    def find_rule(
        self,
        *,
        route_id: str,
        ride_kind: str,
        from_sequence: int,
        to_sequence: int,
        vehicle_type_code: str | None,
        on: date,
    ) -> FareRuleRow | None:
        """The price in force on a given date.

        A rule tied to a specific vehicle type wins over a general one; among
        equals the most recently effective wins, so superseding a price is an
        insert rather than an edit and the history stays intact.
        """
        stmt = (
            self._base()
            .where(
                FareRuleRow.route_id == route_id,
                FareRuleRow.ride_kind == ride_kind,
                FareRuleRow.from_sequence == from_sequence,
                FareRuleRow.to_sequence == to_sequence,
                FareRuleRow.valid_from <= on,
                or_(FareRuleRow.valid_to.is_(None), FareRuleRow.valid_to >= on),
                or_(
                    FareRuleRow.vehicle_type_code.is_(None),
                    FareRuleRow.vehicle_type_code == vehicle_type_code,
                ),
            )
            .order_by(
                FareRuleRow.vehicle_type_code.is_(None),   # specific before general
                FareRuleRow.valid_from.desc(),
            )
            .limit(1)
        )
        return self.session.scalars(stmt).one_or_none()
